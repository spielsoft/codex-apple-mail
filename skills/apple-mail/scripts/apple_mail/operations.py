import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, sleep
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .gmail import (
    GmailClient,
    resolve_messages_parallel,
)
from .gmail_labels import remove_source_labels_with_rollback
from .limits import (
    MAIL_TRANSPORT_CHUNK_SIZE,
    PUBLIC_GMAIL_BATCH_LIMIT,
    chunks,
)
from .mail import MailRunner, MailScriptError
from .plans import (
    GMAIL_TRANSFER_ACTIONS,
    GMAIL_TRANSFER_SOURCE_LABELS,
    require_allowed_destination,
    validate_plan,
)


class OperationError(RuntimeError):
    pass


_WHOLE_PLAN_COPY_BARRIER_DELAYS = (5.0, 5.0)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _message_arguments(messages: Sequence[Dict[str, Any]]) -> List[str]:
    arguments: List[str] = []
    for message in messages:
        arguments.extend(
            [
                str(message["mail_id"]),
                str(message["message_id"]),
                str(message["subject"]),
                str(message.get("sender", "")),
                str(message["received_at"])[:19],
                _bool_text(bool(message["read"])),
            ]
        )
    return arguments


def _source_arguments(source: Dict[str, str]) -> List[str]:
    if source["kind"] == "account":
        return ["account", source["account"], source["mailbox"]]
    return ["local", "", source["path"]]


def _verify_message_group(
    runner: MailRunner,
    plan: Dict[str, Any],
    messages: Sequence[Dict[str, Any]],
) -> List[Dict[str, str]]:
    destination = plan.get("destination")
    arguments = _source_arguments(plan["source"])
    if destination:
        arguments.extend(["local", destination["path"]])
    else:
        arguments.extend(["none", ""])
    arguments.extend(_message_arguments(messages))
    return runner.run_tsv("verify_messages.applescript", arguments)


def verify_messages(
    runner: MailRunner, plan: Dict[str, Any]
) -> List[Dict[str, str]]:
    validate_plan(plan)
    if "messages" not in plan:
        raise OperationError("Mailbox creation plans have no messages to verify")
    messages = plan["messages"]
    if (
        plan["action"] not in GMAIL_TRANSFER_ACTIONS
        or len(messages) <= MAIL_TRANSPORT_CHUNK_SIZE
    ):
        return _verify_message_group(runner, plan, messages)

    rows: List[Dict[str, str]] = []
    source_bulk_count = 0
    for message_group in chunks(messages):
        group_rows = _verify_message_group(runner, plan, message_group)
        if len(group_rows) != len(message_group):
            raise OperationError(
                "Chunked verification returned an unexpected result count"
            )
        group_bulk_counts = {
            row.get("SOURCE_BULK_COUNT", "") for row in group_rows
        }
        if len(group_bulk_counts) != 1:
            raise OperationError(
                "Chunked verification returned inconsistent selector counts"
            )
        try:
            group_bulk_count = int(next(iter(group_bulk_counts)))
        except (TypeError, ValueError) as error:
            raise OperationError(
                "Chunked verification returned an invalid selector count"
            ) from error
        if group_bulk_count < 0 or group_bulk_count > len(message_group):
            raise OperationError(
                "Chunked verification returned an invalid selector count"
            )
        source_bulk_count += group_bulk_count
        rows.extend(group_rows)
    for row in rows:
        row["SOURCE_BULK_COUNT"] = str(source_bulk_count)
    return rows


def probe_account_to_local_copy(
    runner: MailRunner, plan: Dict[str, Any]
) -> Dict[str, str]:
    validate_plan(plan)
    if plan["action"] not in GMAIL_TRANSFER_ACTIONS:
        raise OperationError("Plan is not a Gmail source-to-local transfer")
    if len(plan["messages"]) > PUBLIC_GMAIL_BATCH_LIMIT:
        raise OperationError(
            "Gmail transfer batch size cannot exceed {} messages".format(
                PUBLIC_GMAIL_BATCH_LIMIT
            )
        )
    totals = {
        "ITEM_COUNT": 0,
        "COPY_COUNT": 0,
        "REUSED_COUNT": 0,
        "MISSING_COPY_COUNT": 0,
        "SOURCE_SELECTOR_COUNT": 0,
    }
    ready = True
    source_resolved = True
    destination_resolved = True
    for message_group in chunks(plan["messages"]):
        arguments = [
            "probe",
            plan["source"]["account"],
            plan["source"]["mailbox"],
            plan["destination"]["path"],
        ]
        arguments.extend(_message_arguments(message_group))
        rows = runner.run_tsv(
            "copy_account_to_local.applescript", arguments
        )
        if len(rows) != 1 or rows[0].get("MODE") != "probe":
            raise OperationError(
                "Copy preflight probe returned an unexpected result"
            )
        row = rows[0]
        try:
            for field in totals:
                totals[field] += int(row[field])
        except (KeyError, TypeError, ValueError) as error:
            raise OperationError(
                "Copy preflight probe returned an invalid count"
            ) from error
        ready = ready and row.get("READY") == "true"
        source_resolved = (
            source_resolved and row.get("SOURCE_RESOLVED") == "true"
        )
        destination_resolved = (
            destination_resolved
            and row.get("DESTINATION_RESOLVED") == "true"
        )
    return {
        "MODE": "probe",
        **{field: str(value) for field, value in totals.items()},
        "SOURCE_RESOLVED": _bool_text(source_resolved),
        "DESTINATION_RESOLVED": _bool_text(destination_resolved),
        "READY": _bool_text(ready),
    }


def _source_mismatches(
    rows: Sequence[Dict[str, str]], messages: Sequence[Dict[str, Any]]
) -> List[str]:
    if len(rows) != len(messages):
        return ["result_count"]
    expected_bulk_count = str(len(messages))
    if any(
        row.get("SOURCE_BULK_COUNT") != expected_bulk_count for row in rows
    ):
        return ["bulk_selector_count"]
    expected = {str(item["mail_id"]): item for item in messages}
    positions = {
        str(item["mail_id"]): index
        for index, item in enumerate(messages, start=1)
    }
    mismatches: List[str] = []
    seen = set()
    identity_fields = (
        ("SOURCE_MESSAGE_ID_MATCH", "message_id"),
        ("SOURCE_SUBJECT_MATCH", "subject"),
        ("SOURCE_SENDER_MATCH", "sender"),
        ("SOURCE_RECEIVED_AT_MATCH", "received_at"),
    )
    for row_number, row in enumerate(rows, start=1):
        message = expected.get(row.get("MAIL_ID", ""))
        if message is None:
            mismatches.append("result {} (unexpected_mail_id)".format(row_number))
            continue
        position = positions[str(message["mail_id"])]
        seen.add(str(message["mail_id"]))
        fields = []
        if row.get("SOURCE_ID_COUNT") != "1":
            fields.append("source_id_count")
        if row.get("SOURCE_IDENTITY") != "true":
            detailed_fields = [
                label
                for column, label in identity_fields
                if row.get(column) == "false"
            ]
            fields.extend(detailed_fields or ["identity"])
        if row.get("SOURCE_READ") != _bool_text(bool(message["read"])):
            fields.append("read_state")
        if fields:
            mismatches.append(
                "item {} ({})".format(position, ",".join(fields))
            )
    for mail_id, position in positions.items():
        if mail_id not in seen:
            mismatches.append("item {} (missing_result)".format(position))
    return mismatches


def _require_valid_sources(
    rows: Sequence[Dict[str, str]],
    messages: Sequence[Dict[str, Any]],
    label: str,
) -> None:
    mismatches = _source_mismatches(rows, messages)
    if mismatches:
        raise OperationError("{}: {}".format(label, "; ".join(mismatches)))


def _destinations_are_valid(
    rows: Sequence[Dict[str, str]],
    messages: Sequence[Dict[str, Any]],
    *,
    required: bool,
) -> bool:
    expected = {str(item["mail_id"]): item for item in messages}
    for row in rows:
        message = expected.get(row.get("MAIL_ID", ""))
        if message is None:
            return False
        count = row.get("DESTINATION_COUNT")
        if required:
            if count != "1":
                return False
            if row.get("DESTINATION_READ") != _bool_text(bool(message["read"])):
                return False
        elif count not in ("0", "1"):
            return False
        elif count == "1" and row.get("DESTINATION_READ") != _bool_text(
            bool(message["read"])
        ):
            return False
    return True


def _copy_barrier_is_valid(
    rows: Sequence[Dict[str, str]],
    messages: Sequence[Dict[str, Any]],
) -> bool:
    if len(rows) != len(messages):
        return False
    expected = {str(item["mail_id"]): item for item in messages}
    seen = set()
    for row in rows:
        mail_id = row.get("MAIL_ID", "")
        message = expected.get(mail_id)
        if message is None or mail_id in seen:
            return False
        seen.add(mail_id)
        if row.get("STATUS") not in ("COPIED", "REUSED"):
            return False
        if row.get("DESTINATION_COUNT") != "1":
            return False
        if row.get("DESTINATION_IDENTITY") != "true":
            return False
        if row.get("DESTINATION_READ") != _bool_text(bool(message["read"])):
            return False
    return len(seen) == len(messages)


def _copy_barrier_summary(
    rows: Sequence[Dict[str, str]],
) -> Dict[str, int]:
    attempts = []
    for row in rows:
        try:
            attempts.append(int(row.get("BARRIER_ATTEMPTS", "0")))
        except (TypeError, ValueError):
            pass
    return {
        "local_copies_submitted": sum(
            row.get("STATUS") == "COPIED" for row in rows
        ),
        "local_copies_reused": sum(
            row.get("STATUS") == "REUSED" for row in rows
        ),
        "local_copy_barrier_attempts": max(attempts or [0]),
    }


def _verify_whole_plan_copy_barrier(
    runner: MailRunner,
    plan: Dict[str, Any],
) -> tuple:
    attempts = 0
    for delay in _WHOLE_PLAN_COPY_BARRIER_DELAYS:
        sleep(delay)
        attempts += 1
        try:
            rows = verify_messages(runner, plan)
        except (MailScriptError, OperationError):
            continue
        if (
            not _source_mismatches(rows, plan["messages"])
            and _destinations_are_valid(
                rows,
                plan["messages"],
                required=True,
            )
        ):
            return True, attempts
    return False, attempts


def _append_audit(path: Optional[Path], event: Dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def append_audit_event(path: Path, event: Dict[str, Any]) -> None:
    _append_audit(path, event)


def _elapsed(started_at: float) -> float:
    return round(perf_counter() - started_at, 3)


def _require_recoverable_gmail_audit(
    audit_path: Optional[Path],
    plan: Dict[str, Any],
) -> None:
    if audit_path is None or not audit_path.is_file():
        raise OperationError(
            "Gmail resume requires the existing audit file"
        )
    try:
        events = [
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, ValueError) as error:
        raise OperationError("Gmail resume audit is unreadable") from error
    matching = [
        event
        for event in events
        if (
            event.get("action") == plan["action"]
            and event.get("plan_hash") == plan["plan_hash"]
        )
    ]
    if (
        not matching
        or matching[-1].get("status")
        not in ("operation_failed", "mutation_state_unknown")
        or not any(
            event.get("status") == "operation_started"
            for event in matching[:-1]
        )
    ):
        raise OperationError(
            "Gmail resume requires a prior started and failed audit lifecycle"
        )


def _require_valid_resume_destinations(
    rows: Sequence[Dict[str, str]],
    messages: Sequence[Dict[str, Any]],
) -> None:
    if len(rows) != len(messages):
        raise OperationError(
            "Gmail resume destination verification returned an "
            "unexpected count"
        )
    for row, message in zip(rows, messages):
        if (
            row.get("MAIL_ID") != str(message["mail_id"])
            or row.get("DESTINATION_COUNT") != "1"
            or row.get("DESTINATION_READ")
            != _bool_text(bool(message["read"]))
        ):
            raise OperationError(
                "Gmail resume requires one exact read-preserved "
                "destination copy for every planned message"
            )


def apply_local_move(
    runner: MailRunner,
    plan: Dict[str, Any],
    *,
    allowed_destinations: Iterable[str],
    audit_path: Optional[Path] = None,
) -> Dict[str, Any]:
    require_allowed_destination(plan, allowed_destinations)
    if plan["action"] != "move_local":
        raise OperationError("Plan is not a local move")
    before = verify_messages(runner, plan)
    _require_valid_sources(
        before, plan["messages"], "Local source preflight failed"
    )
    if not _destinations_are_valid(before, plan["messages"], required=False):
        raise OperationError("Local destination preflight failed")
    if any(row["DESTINATION_COUNT"] != "0" for row in before):
        raise OperationError("Destination already contains a planned message")
    _append_audit(
        audit_path,
        {
            "status": "operation_started",
            "action": plan["action"],
            "plan_hash": plan["plan_hash"],
            "message_count": len(plan["messages"]),
        },
    )
    arguments = [
        plan["source"]["path"],
        plan["destination"]["path"],
        "apply",
    ]
    arguments.extend(_message_arguments(plan["messages"]))
    runner.run_tsv("move_local_messages.applescript", arguments)
    after = verify_messages(runner, plan)
    if any(row["SOURCE_ID_COUNT"] != "0" for row in after):
        raise OperationError("A moved message still resolves in the source by numeric ID")
    if not _destinations_are_valid(after, plan["messages"], required=True):
        raise OperationError("Local destination verification failed")
    result = {
        "status": "complete",
        "action": plan["action"],
        "plan_hash": plan["plan_hash"],
        "message_count": len(plan["messages"]),
    }
    _append_audit(audit_path, result)
    return result


def apply_set_read(
    runner: MailRunner,
    plan: Dict[str, Any],
    *,
    audit_path: Optional[Path] = None,
) -> Dict[str, Any]:
    validate_plan(plan)
    if plan["action"] != "set_read":
        raise OperationError("Plan is not a read-state change")
    before = verify_messages(runner, plan)
    _require_valid_sources(
        before, plan["messages"], "Read-state source preflight failed"
    )
    _append_audit(
        audit_path,
        {
            "status": "operation_started",
            "action": plan["action"],
            "plan_hash": plan["plan_hash"],
            "message_count": len(plan["messages"]),
        },
    )
    arguments = _source_arguments(plan["source"])
    arguments.append(_bool_text(plan["target_read"]))
    arguments.extend(_message_arguments(plan["messages"]))
    runner.run_tsv("set_read_messages.applescript", arguments)
    after = verify_messages(runner, plan)
    if len(after) != len(plan["messages"]):
        raise OperationError("Read-state verification returned an unexpected count")
    for row in after:
        if (
            row["SOURCE_ID_COUNT"] != "1"
            or row["SOURCE_IDENTITY"] != "true"
            or row["SOURCE_READ"] != _bool_text(plan["target_read"])
        ):
            raise OperationError("Read-state verification failed")
    result = {
        "status": "complete",
        "action": plan["action"],
        "plan_hash": plan["plan_hash"],
        "message_count": len(plan["messages"]),
        "target_read": plan["target_read"],
    }
    _append_audit(audit_path, result)
    return result


def apply_create_mailbox(
    runner: MailRunner,
    plan: Dict[str, Any],
    *,
    allowed_destinations: Iterable[str],
    audit_path: Optional[Path] = None,
) -> Dict[str, Any]:
    require_allowed_destination(plan, allowed_destinations)
    if plan["action"] != "create_local_mailbox":
        raise OperationError("Plan is not a mailbox creation")
    _append_audit(
        audit_path,
        {
            "status": "operation_started",
            "action": plan["action"],
            "plan_hash": plan["plan_hash"],
        },
    )
    rows = runner.run_tsv(
        "create_local_mailbox.applescript", [plan["destination"]["path"]]
    )
    if len(rows) != 1 or rows[0].get("STATUS") not in ("CREATED", "EXISTS"):
        raise OperationError("Mailbox creation returned an unexpected result")
    result = {
        "status": "complete",
        "action": plan["action"],
        "plan_hash": plan["plan_hash"],
        "mailbox_status": rows[0]["STATUS"].lower(),
    }
    _append_audit(audit_path, result)
    return result


def _apply_gmail_source_to_local(
    runner: MailRunner,
    client: GmailClient,
    plan: Dict[str, Any],
    *,
    expected_account: str,
    allowed_destinations: Iterable[str],
    audit_path: Optional[Path] = None,
    resume: bool = False,
) -> Dict[str, Any]:
    transaction_started = perf_counter()
    phase_seconds: Dict[str, float] = {}
    require_allowed_destination(plan, allowed_destinations)
    source_label = GMAIL_TRANSFER_SOURCE_LABELS.get(plan["action"])
    if source_label is None:
        raise OperationError("Plan is not a Gmail source-to-local transfer")
    if len(plan["messages"]) > PUBLIC_GMAIL_BATCH_LIMIT:
        raise OperationError(
            "Gmail transfer batch size cannot exceed {} messages".format(
                PUBLIC_GMAIL_BATCH_LIMIT
            )
        )
    phase_started = perf_counter()
    profile = client.profile()
    phase_seconds["gmail_profile"] = _elapsed(phase_started)
    if str(profile.get("emailAddress", "")).casefold() != expected_account.casefold():
        raise OperationError("Authenticated Gmail profile does not match the plan")
    if plan["source"]["account"].casefold() != expected_account.casefold():
        raise OperationError("Plan account does not match the expected Gmail account")

    phase_started = perf_counter()
    gmail_messages = resolve_messages_parallel(client, plan["messages"])
    phase_seconds["gmail_preflight"] = _elapsed(phase_started)
    if resume:
        _require_recoverable_gmail_audit(audit_path, plan)
    for gmail_message in gmail_messages:
        labels = set(gmail_message.get("labelIds", []))
        if resume:
            invalid_labels = (
                "TRASH" in labels
                or (source_label == "INBOX" and "SPAM" in labels)
                or (
                    source_label == "SPAM"
                    and "INBOX" in labels
                )
            )
        else:
            invalid_labels = (
                source_label not in labels
                or "TRASH" in labels
                or (
                    source_label == "INBOX"
                    and "SPAM" in labels
                )
                or (
                    source_label == "SPAM"
                    and "INBOX" in labels
                )
            )
        if invalid_labels:
            raise OperationError(
                "Gmail source labels do not match the required pre-state"
            )

    if resume:
        phase_started = perf_counter()
        destination_rows = verify_messages(runner, plan)
        _require_valid_resume_destinations(
            destination_rows,
            plan["messages"],
        )
        phase_seconds["local_copy"] = _elapsed(phase_started)

    _append_audit(
        audit_path,
        {
            "status": "operation_started",
            "action": plan["action"],
            "plan_hash": plan["plan_hash"],
            "message_count": len(plan["messages"]),
            **({"resume": True} if resume else {}),
        },
    )
    if resume:
        copy_summary = {
            "local_copies_submitted": 0,
            "local_copies_reused": len(plan["messages"]),
            "local_copy_barrier_attempts": 0,
        }
    else:
        phase_started = perf_counter()
        copied: List[Dict[str, str]] = []
        for message_group in chunks(plan["messages"]):
            arguments = [
                "submit",
                plan["source"]["account"],
                plan["source"]["mailbox"],
                plan["destination"]["path"],
            ]
            arguments.extend(_message_arguments(message_group))
            group_rows = runner.run_tsv(
                "copy_account_to_local.applescript", arguments
            )
            copied.extend(group_rows)
        copy_summary = _copy_barrier_summary(copied)
        copy_barrier_valid = _copy_barrier_is_valid(
            copied,
            plan["messages"],
        )
        barrier_attempts = 0
        if not copy_barrier_valid:
            copy_barrier_valid, barrier_attempts = (
                _verify_whole_plan_copy_barrier(runner, plan)
            )
        copy_summary["local_copy_barrier_attempts"] = barrier_attempts
        phase_seconds["local_copy"] = _elapsed(phase_started)
        if not copy_barrier_valid:
            phase_seconds["transaction_total"] = _elapsed(
                transaction_started
            )
            result = {
                "status": "pending_local_copy",
                "action": plan["action"],
                "plan_hash": plan["plan_hash"],
                **copy_summary,
                "phase_seconds": phase_seconds,
            }
            _append_audit(audit_path, result)
            return result

    phase_started = perf_counter()
    source_messages = [
        message
        for message in gmail_messages
        if source_label in set(message.get("labelIds", []))
    ]
    changed_ids = (
        remove_source_labels_with_rollback(
            client,
            source_messages,
            source_label,
        )
        if source_messages
        else []
    )
    phase_seconds["gmail_label_removal"] = _elapsed(phase_started)

    phase_started = perf_counter()
    runner.run_raw("synchronize_account.applescript", [plan["source"]["account"]])
    phase_seconds["mail_synchronize"] = _elapsed(phase_started)
    phase_seconds["transaction_total"] = _elapsed(transaction_started)
    result = {
        "status": "pending_mail_sync",
        "action": plan["action"],
        "plan_hash": plan["plan_hash"],
        "message_count": len(plan["messages"]),
        "gmail_source_labels_removed": len(changed_ids),
        **copy_summary,
        "phase_seconds": phase_seconds,
    }
    result[
        "gmail_{}_labels_removed".format(source_label.casefold())
    ] = len(changed_ids)
    if resume:
        result["gmail_source_labels_already_absent"] = (
            len(gmail_messages) - len(source_messages)
        )
        result["resume"] = True
    _append_audit(audit_path, result)
    return result


def apply_gmail_inbox_to_local(
    runner: MailRunner,
    client: GmailClient,
    plan: Dict[str, Any],
    *,
    expected_account: str,
    allowed_destinations: Iterable[str],
    audit_path: Optional[Path] = None,
    resume: bool = False,
) -> Dict[str, Any]:
    if plan.get("action") != "gmail_inbox_to_local":
        raise OperationError("Plan is not a Gmail Inbox-to-local transfer")
    return _apply_gmail_source_to_local(
        runner,
        client,
        plan,
        expected_account=expected_account,
        allowed_destinations=allowed_destinations,
        audit_path=audit_path,
        resume=resume,
    )


def apply_gmail_spam_to_local(
    runner: MailRunner,
    client: GmailClient,
    plan: Dict[str, Any],
    *,
    expected_account: str,
    allowed_destinations: Iterable[str],
    audit_path: Optional[Path] = None,
    resume: bool = False,
) -> Dict[str, Any]:
    if plan.get("action") != "gmail_spam_to_local":
        raise OperationError("Plan is not a Gmail Spam-to-local transfer")
    return _apply_gmail_source_to_local(
        runner,
        client,
        plan,
        expected_account=expected_account,
        allowed_destinations=allowed_destinations,
        audit_path=audit_path,
        resume=resume,
    )
