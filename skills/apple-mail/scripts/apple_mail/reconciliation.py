from pathlib import Path
from typing import Any, Dict, List, Sequence

from .mail import MailRunner
from .operations import append_audit_event, verify_messages
from .plans import GMAIL_TRANSFER_ACTIONS, validate_plan


COMPLETE = "complete"
PENDING_MAIL_SYNC = "pending_mail_sync"
MUTATION_STATE_UNKNOWN = "mutation_state_unknown"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _result(
    plan: Dict[str, Any],
    status: str,
    *,
    destination_valid_count: int,
    source_absent_count: int,
    source_exact_count: int,
    reason_codes: Sequence[str] = (),
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": status,
        "action": plan["action"],
        "plan_hash": plan["plan_hash"],
        "message_count": len(plan["messages"]),
        "destination_valid_count": destination_valid_count,
        "source_absent_count": source_absent_count,
        "source_exact_count": source_exact_count,
    }
    if reason_codes:
        result["reason_codes"] = sorted(set(reason_codes))
    return result


def classify_gmail_transfer_state(
    plan: Dict[str, Any],
    rows: Sequence[Dict[str, str]],
) -> Dict[str, Any]:
    """Classify a bounded Mail verification without exposing message details."""
    validate_plan(plan)
    if plan["action"] not in GMAIL_TRANSFER_ACTIONS:
        raise ValueError("Reconciliation requires a Gmail source-to-local plan")

    messages = plan["messages"]
    expected = {str(message["mail_id"]): message for message in messages}
    reasons: List[str] = []

    if len(rows) != len(messages):
        reasons.append("verification_result_count")

    indexed_rows: Dict[str, Dict[str, str]] = {}
    for row in rows:
        mail_id = row.get("MAIL_ID", "")
        if mail_id not in expected:
            reasons.append("verification_unexpected_mail_id")
            continue
        if mail_id in indexed_rows:
            reasons.append("verification_duplicate_mail_id")
            continue
        indexed_rows[mail_id] = row

    destination_valid_count = 0
    source_absent_count = 0
    source_exact_count = 0
    bulk_counts = set()
    identity_columns = (
        "SOURCE_IDENTITY",
        "SOURCE_MESSAGE_ID_MATCH",
        "SOURCE_SUBJECT_MATCH",
        "SOURCE_SENDER_MATCH",
        "SOURCE_RECEIVED_AT_MATCH",
    )

    for mail_id, message in expected.items():
        row = indexed_rows.get(mail_id)
        if row is None:
            reasons.append("verification_missing_result")
            continue

        bulk_counts.add(row.get("SOURCE_BULK_COUNT", ""))
        if (
            row.get("DESTINATION_COUNT") == "1"
            and row.get("DESTINATION_READ")
            == _bool_text(bool(message["read"]))
        ):
            destination_valid_count += 1
        else:
            reasons.append("destination_copy_state")

        source_count = row.get("SOURCE_ID_COUNT")
        if source_count == "0":
            source_absent_count += 1
        elif (
            source_count == "1"
            and all(row.get(column) == "true" for column in identity_columns)
            and row.get("SOURCE_READ") == _bool_text(bool(message["read"]))
        ):
            source_exact_count += 1
        else:
            reasons.append("source_identity_state")

    message_count = len(messages)
    all_destinations_valid = destination_valid_count == message_count
    all_sources_accounted_for = (
        source_absent_count + source_exact_count == message_count
    )
    expected_bulk_count = (
        str(source_exact_count) if all_sources_accounted_for else None
    )
    if expected_bulk_count is None or bulk_counts != {expected_bulk_count}:
        reasons.append("bulk_selector_count")

    if (
        not reasons
        and all_destinations_valid
        and all_sources_accounted_for
        and source_exact_count == 0
    ):
        return _result(
            plan,
            COMPLETE,
            destination_valid_count=destination_valid_count,
            source_absent_count=source_absent_count,
            source_exact_count=source_exact_count,
        )
    if not reasons and all_destinations_valid and all_sources_accounted_for:
        return _result(
            plan,
            PENDING_MAIL_SYNC,
            destination_valid_count=destination_valid_count,
            source_absent_count=source_absent_count,
            source_exact_count=source_exact_count,
        )
    return _result(
        plan,
        MUTATION_STATE_UNKNOWN,
        destination_valid_count=destination_valid_count,
        source_absent_count=source_absent_count,
        source_exact_count=source_exact_count,
        reason_codes=reasons or ("unclassified_state",),
    )


def reconcile_gmail_transfer(
    runner: MailRunner,
    plan: Dict[str, Any],
    *,
    audit_path: Path,
) -> Dict[str, Any]:
    """Verify, classify, and audit a Gmail transfer without mutating anything."""
    validate_plan(plan)
    if plan["action"] not in GMAIL_TRANSFER_ACTIONS:
        raise ValueError("Reconciliation requires a Gmail source-to-local plan")
    try:
        rows = verify_messages(runner, plan)
        result = classify_gmail_transfer_state(plan, rows)
    except Exception:
        result = _result(
            plan,
            MUTATION_STATE_UNKNOWN,
            destination_valid_count=0,
            source_absent_count=0,
            source_exact_count=0,
            reason_codes=("verification_unavailable",),
        )
    append_audit_event(audit_path, result)
    return result
