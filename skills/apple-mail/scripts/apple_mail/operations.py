import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .gmail import (
    GmailClient,
    GmailError,
    resolve_unique_message,
    validate_archived_labels,
)
from .mail import MailRunner
from .plans import require_allowed_destination, validate_plan


class OperationError(RuntimeError):
    pass


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


def verify_messages(
    runner: MailRunner, plan: Dict[str, Any]
) -> List[Dict[str, str]]:
    validate_plan(plan)
    if "messages" not in plan:
        raise OperationError("Mailbox creation plans have no messages to verify")
    destination = plan.get("destination")
    arguments = _source_arguments(plan["source"])
    if destination:
        arguments.extend(["local", destination["path"]])
    else:
        arguments.extend(["none", ""])
    arguments.extend(_message_arguments(plan["messages"]))
    return runner.run_tsv("verify_messages.applescript", arguments)


def probe_account_to_local_copy(
    runner: MailRunner, plan: Dict[str, Any]
) -> Dict[str, str]:
    validate_plan(plan)
    if plan["action"] != "gmail_inbox_to_local":
        raise OperationError("Plan is not a Gmail Inbox-to-local transfer")
    if len(plan["messages"]) > 10:
        raise OperationError("Gmail transfer batch size cannot exceed 10 messages")
    arguments = [
        "probe",
        plan["source"]["account"],
        plan["source"]["mailbox"],
        plan["destination"]["path"],
    ]
    arguments.extend(_message_arguments(plan["messages"]))
    rows = runner.run_tsv("copy_account_to_local.applescript", arguments)
    if len(rows) != 1 or rows[0].get("MODE") != "probe":
        raise OperationError("Copy preflight probe returned an unexpected result")
    return rows[0]


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


def apply_gmail_inbox_to_local(
    runner: MailRunner,
    client: GmailClient,
    plan: Dict[str, Any],
    *,
    expected_account: str,
    allowed_destinations: Iterable[str],
    audit_path: Optional[Path] = None,
) -> Dict[str, Any]:
    require_allowed_destination(plan, allowed_destinations)
    if plan["action"] != "gmail_inbox_to_local":
        raise OperationError("Plan is not a Gmail Inbox-to-local transfer")
    if len(plan["messages"]) > 10:
        raise OperationError("Gmail transfer batch size cannot exceed 10 messages")
    profile = client.profile()
    if str(profile.get("emailAddress", "")).casefold() != expected_account.casefold():
        raise OperationError("Authenticated Gmail profile does not match the plan")
    if plan["source"]["account"].casefold() != expected_account.casefold():
        raise OperationError("Plan account does not match the expected Gmail account")

    gmail_messages = []
    for message in plan["messages"]:
        gmail_message = resolve_unique_message(client, message)
        labels = set(gmail_message.get("labelIds", []))
        if "INBOX" not in labels or "TRASH" in labels:
            raise OperationError("Gmail source labels do not match the required pre-state")
        gmail_messages.append(gmail_message)

    before = verify_messages(runner, plan)
    _require_valid_sources(
        before, plan["messages"], "Mail source preflight failed"
    )
    if not _destinations_are_valid(before, plan["messages"], required=False):
        raise OperationError("Local destination preflight failed")

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
        "apply",
        plan["source"]["account"],
        plan["source"]["mailbox"],
        plan["destination"]["path"],
    ]
    arguments.extend(_message_arguments(plan["messages"]))
    copied = runner.run_tsv("copy_account_to_local.applescript", arguments)
    if not _copy_barrier_is_valid(copied, plan["messages"]):
        result = {
            "status": "pending_local_copy",
            "action": plan["action"],
            "plan_hash": plan["plan_hash"],
        }
        _append_audit(audit_path, result)
        return result

    changed_ids: List[str] = []
    try:
        for gmail_message in gmail_messages:
            changed = client.modify_inbox_label(gmail_message["id"], remove=True)
            validate_archived_labels(changed)
            changed_ids.append(gmail_message["id"])
    except Exception:
        rollback_errors = []
        for gmail_id in reversed(changed_ids):
            try:
                client.modify_inbox_label(gmail_id, add=True)
            except GmailError as error:
                rollback_errors.append(str(error))
        if rollback_errors:
            raise OperationError(
                "Gmail mutation failed and rollback was incomplete: {}".format(
                    "; ".join(rollback_errors)
                )
            )
        raise

    runner.run_raw("synchronize_account.applescript", [plan["source"]["account"]])
    final = verify_messages(runner, plan)
    if not _destinations_are_valid(final, plan["messages"], required=True):
        raise OperationError("Final local destination verification failed")
    if any(
        row["SOURCE_ID_COUNT"] == "1" and row["SOURCE_IDENTITY"] != "true"
        for row in final
    ):
        raise OperationError("A numeric source ID was reused by another message")
    source_pending = any(row["SOURCE_ID_COUNT"] == "1" for row in final)
    result = {
        "status": "pending_mail_sync" if source_pending else "complete",
        "action": plan["action"],
        "plan_hash": plan["plan_hash"],
        "message_count": len(plan["messages"]),
        "gmail_inbox_labels_removed": len(changed_ids),
    }
    _append_audit(audit_path, result)
    return result
