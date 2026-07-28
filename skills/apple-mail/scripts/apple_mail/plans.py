import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 1
PLAN_KIND = "apple_mail_operation_plan"
MESSAGE_ACTIONS = {
    "gmail_inbox_to_local",
    "move_local",
    "set_read",
}
ALL_ACTIONS = MESSAGE_ACTIONS | {"create_local_mailbox"}
LOCAL_PATH_PREFIX = "On My Mac/"
PROTECTED_LOCAL_LEAVES = {
    "deleted messages",
    "drafts",
    "junk",
    "junk mail",
    "outbox",
    "send later",
    "sendlater",
    "sent",
    "sent messages",
    "trash",
}


class PlanError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def calculate_plan_hash(plan_without_hash: Dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json(plan_without_hash).encode("utf-8")
    ).hexdigest()


def validate_local_path(path: str, *, destination: bool = False) -> None:
    if not isinstance(path, str) or not path.startswith(LOCAL_PATH_PREFIX):
        raise PlanError("Local mailbox path must begin with 'On My Mac/'")
    relative = path[len(LOCAL_PATH_PREFIX) :]
    parts = relative.split("/")
    if (
        not relative
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or any(not part or part in (".", "..") for part in parts)
    ):
        raise PlanError("Invalid local mailbox path")
    if destination and parts[-1].casefold() in PROTECTED_LOCAL_LEAVES:
        raise PlanError("Destination is a protected Mail mailbox")


def account_source(account: str, mailbox: str = "INBOX") -> Dict[str, str]:
    if not account or not mailbox:
        raise PlanError("Account source requires account and mailbox")
    return {"kind": "account", "account": account, "mailbox": mailbox}


def local_source(path: str) -> Dict[str, str]:
    validate_local_path(path)
    return {"kind": "local", "path": path}


def local_destination(path: str) -> Dict[str, str]:
    validate_local_path(path, destination=True)
    return {"kind": "local", "path": path}


def _selection_message(selection: Dict[str, Any]) -> Dict[str, Any]:
    raw_mail_id = selection.get("mail_id")
    if raw_mail_id is None:
        raw_mail_id = selection.get("local_id")
    if raw_mail_id is None:
        raw_mail_id = selection.get("current_local_id")
    try:
        mail_id = int(raw_mail_id)
    except (TypeError, ValueError):
        raise PlanError("Message selection requires a positive numeric mail_id")
    if mail_id < 1:
        raise PlanError("Message selection requires a positive numeric mail_id")
    raw_read = selection.get("read")
    if isinstance(raw_read, bool):
        read = raw_read
    elif isinstance(raw_read, str) and raw_read.casefold() in ("true", "false"):
        read = raw_read.casefold() == "true"
    else:
        raise PlanError("Message selection requires a Boolean read state")
    message = {
        "mail_id": mail_id,
        "message_id": str(selection.get("message_id", "")).strip(),
        "subject": str(selection.get("subject", "")),
        "sender": str(selection.get("sender", "")),
        "received_at": str(selection.get("received_at", "")),
        "read": read,
    }
    for key in ("message_id", "received_at"):
        if not message[key]:
            raise PlanError("Message selection is missing {}".format(key))
    try:
        datetime.strptime(message["received_at"][:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        raise PlanError("Message selection has an invalid received_at")
    return message


def build_message_plan(
    action: str,
    source: Dict[str, str],
    selections: Iterable[Dict[str, Any]],
    *,
    destination: Optional[Dict[str, str]] = None,
    target_read: Optional[bool] = None,
) -> Dict[str, Any]:
    plan: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "action": action,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": dict(source),
        "messages": [_selection_message(item) for item in selections],
    }
    if destination is not None:
        plan["destination"] = dict(destination)
    if target_read is not None:
        plan["target_read"] = bool(target_read)
    if not plan["messages"]:
        raise PlanError("A message plan must contain at least one message")
    plan["plan_hash"] = calculate_plan_hash(plan)
    validate_plan(plan)
    return plan


def build_create_mailbox_plan(path: str) -> Dict[str, Any]:
    validate_local_path(path, destination=True)
    plan: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "action": "create_local_mailbox",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "destination": {"kind": "local", "path": path},
    }
    plan["plan_hash"] = calculate_plan_hash(plan)
    validate_plan(plan)
    return plan


def _validate_source(source: Any, *, require_inbox: bool = False) -> None:
    if not isinstance(source, dict):
        raise PlanError("Plan source is missing")
    if source.get("kind") == "local":
        if set(source) != {"kind", "path"}:
            raise PlanError("Local source fields are not canonical")
        validate_local_path(source.get("path", ""))
    elif source.get("kind") == "account":
        if set(source) != {"kind", "account", "mailbox"}:
            raise PlanError("Account source fields are not canonical")
        if not source.get("account") or not source.get("mailbox"):
            raise PlanError("Account source requires account and mailbox")
        if require_inbox and source.get("mailbox") != "INBOX":
            raise PlanError("Gmail transfer source must be account-qualified INBOX")
    else:
        raise PlanError("Unsupported source kind")


def _validate_destination(destination: Any) -> None:
    if not isinstance(destination, dict) or destination.get("kind") != "local":
        raise PlanError("Destination must be a local mailbox")
    if set(destination) != {"kind", "path"}:
        raise PlanError("Destination fields are not canonical")
    validate_local_path(destination.get("path", ""), destination=True)


def validate_plan(plan: Dict[str, Any]) -> None:
    if plan.get("schema_version") != SCHEMA_VERSION or plan.get("kind") != PLAN_KIND:
        raise PlanError("Unsupported Apple Mail plan schema")
    action = plan.get("action")
    if action not in ALL_ACTIONS:
        raise PlanError("Unsupported Apple Mail plan action")
    stored_hash = plan.get("plan_hash")
    if not isinstance(stored_hash, str):
        raise PlanError("Missing plan hash")
    unhashed = dict(plan)
    del unhashed["plan_hash"]
    if calculate_plan_hash(unhashed) != stored_hash:
        raise PlanError("Plan hash mismatch")

    if action == "create_local_mailbox":
        if set(plan) != {
            "schema_version",
            "kind",
            "action",
            "created_at",
            "destination",
            "plan_hash",
        }:
            raise PlanError("Mailbox creation plan fields are not canonical")
        _validate_destination(plan.get("destination"))
        if "messages" in plan or "source" in plan:
            raise PlanError("Mailbox creation plan has unexpected message fields")
        return

    messages = plan.get("messages")
    expected_fields = {
        "schema_version",
        "kind",
        "action",
        "created_at",
        "source",
        "messages",
        "plan_hash",
    }
    if action in ("gmail_inbox_to_local", "move_local"):
        expected_fields.add("destination")
    if action == "set_read":
        expected_fields.add("target_read")
    if set(plan) != expected_fields:
        raise PlanError("Plan fields are not canonical")
    if not isinstance(messages, list) or not messages:
        raise PlanError("Plan has no messages")
    if len(messages) > 250:
        raise PlanError("Plan exceeds the maximum batch size of 250")
    seen = set()
    for message in messages:
        validated = _selection_message(message)
        if message != validated:
            raise PlanError("Plan message fields are not canonical")
        identity = (validated["mail_id"], validated["message_id"].casefold())
        if identity in seen:
            raise PlanError("Plan contains a duplicate message identity")
        seen.add(identity)

    _validate_source(
        plan.get("source"), require_inbox=action == "gmail_inbox_to_local"
    )
    if action in ("gmail_inbox_to_local", "move_local"):
        _validate_destination(plan.get("destination"))
    elif "destination" in plan:
        raise PlanError("Read-state plan has an unexpected destination")

    if action == "gmail_inbox_to_local" and plan["source"]["kind"] != "account":
        raise PlanError("Gmail transfer source must be an account mailbox")
    if action == "move_local":
        if plan["source"]["kind"] != "local":
            raise PlanError("Local move source must be a local mailbox")
        if plan["source"]["path"] == plan["destination"]["path"]:
            raise PlanError("Local source and destination must differ")
    if action == "set_read":
        if not isinstance(plan.get("target_read"), bool):
            raise PlanError("Read-state plan requires target_read")


def require_allowed_destination(
    plan: Dict[str, Any], allowed_destinations: Iterable[str]
) -> None:
    validate_plan(plan)
    destination = plan.get("destination")
    if destination is None:
        return
    allowed = set(allowed_destinations)
    if destination["path"] not in allowed:
        raise PlanError(
            "Plan destination was not explicitly allowed for this invocation"
        )


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
