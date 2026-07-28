import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from .gmail import (
    GmailBodyUnavailable,
    GmailClient,
    get_message_records_parallel,
)
from .gmail_labels import GmailMutationStateUnknown
from .limits import PUBLIC_GMAIL_BATCH_LIMIT
from .mail import MailRunner
from .oauth import TokenStore, authorize_desktop
from .operations import (
    append_audit_event,
    apply_create_mailbox,
    apply_gmail_inbox_to_local,
    apply_gmail_spam_to_local,
    apply_local_move,
    apply_set_read,
    probe_account_to_local_copy,
    verify_messages,
)
from .plans import (
    account_source,
    build_create_mailbox_plan,
    build_message_plan,
    local_destination,
    local_source,
    read_json,
    require_allowed_destination,
    validate_plan,
    write_json,
)
from .reconciliation import reconcile_gmail_transfer


PACKAGE_DIR = Path(__file__).resolve().parent
APPLESCRIPT_DIR = PACKAGE_DIR / "applescript"


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _source_from_args(args: argparse.Namespace) -> Dict[str, str]:
    if getattr(args, "local", None):
        return local_source(args.local)
    return account_source(args.account, args.mailbox)


def _source_script_arguments(source: Dict[str, str]) -> List[str]:
    if source["kind"] == "account":
        return ["account", source["account"], source["mailbox"]]
    return ["local", "", source["path"]]


def _selection_records(path: Path) -> List[Dict[str, Any]]:
    value = read_json(path)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("messages", "items", "records"):
            if isinstance(value.get(key), list):
                return value[key]
    raise ValueError("Selection JSON must be a list or contain messages/items/records")


def _write_plan(plan: Dict[str, Any], output: Path) -> None:
    write_json(output, plan)
    _print_json(
        {
            "status": "planned",
            "action": plan["action"],
            "plan_hash": plan["plan_hash"],
            "output": str(output),
            "message_count": len(plan.get("messages", [])),
        }
    )


def command_discover(args: argparse.Namespace) -> None:
    _print_json(MailRunner(APPLESCRIPT_DIR, args.timeout).run_tsv(
        "discover_mailboxes.applescript"
    ))


def command_list(args: argparse.Namespace) -> None:
    source = _source_from_args(args)
    arguments = _source_script_arguments(source) + [str(args.start), str(args.limit)]
    _print_json(
        MailRunner(APPLESCRIPT_DIR, args.timeout).run_tsv(
            "list_messages.applescript", arguments
        )
    )


def command_get(args: argparse.Namespace) -> None:
    source = _source_from_args(args)
    arguments = _source_script_arguments(source)
    arguments.extend([str(args.mail_id), args.message_id, str(args.body_limit)])
    _print_json(
        MailRunner(APPLESCRIPT_DIR, args.timeout).run_tsv(
            "get_message.applescript", arguments
        )
    )


def _get_batch_from_mail(
    source: Dict[str, str],
    messages: List[Dict[str, Any]],
    *,
    body_limit: int,
    timeout: int,
) -> List[Dict[str, Any]]:
    arguments = _source_script_arguments(source) + [str(body_limit)]
    for message in messages:
        arguments.extend(
            [
                str(message["mail_id"]),
                str(message["message_id"]),
                str(message["subject"]),
                str(message.get("sender", "")),
                str(message["received_at"])[:19],
                "true" if message["read"] else "false",
            ]
        )
    records = MailRunner(APPLESCRIPT_DIR, timeout).run_tsv(
        "get_messages.applescript", arguments
    )
    for record in records:
        if record.get("TYPE") == "MESSAGE":
            record["ATTACHMENT_COUNT_SOURCE"] = "apple_mail"
    return records


def command_get_batch(args: argparse.Namespace) -> None:
    source = _source_from_args(args)
    plan = build_message_plan(
        "set_read",
        source,
        _selection_records(args.selection),
        target_read=True,
    )
    messages = plan["messages"]
    if len(messages) > PUBLIC_GMAIL_BATCH_LIMIT:
        raise ValueError(
            "Body batch size cannot exceed {} messages".format(
                PUBLIC_GMAIL_BATCH_LIMIT
            )
        )
    token = getattr(args, "token", None)
    if token is not None:
        expected_account = getattr(args, "expected_account", None)
        if (
            source["kind"] != "account"
            or not expected_account
        ):
            raise ValueError(
                "OAuth-backed get-batch requires an account-qualified "
                "mailbox and --expected-account"
            )
        if source["account"].casefold() != expected_account.casefold():
            raise ValueError("Mail account does not match --expected-account")
        client = GmailClient(TokenStore(token))
        profile = client.profile()
        if str(profile.get("emailAddress", "")).casefold() != (
            expected_account.casefold()
        ):
            raise ValueError("Authenticated Gmail profile does not match the account")
        try:
            records = get_message_records_parallel(
                client,
                messages,
                body_limit=args.body_limit,
            )
        except GmailBodyUnavailable:
            print(
                "Gmail body is unavailable inline; using bounded Apple Mail "
                "retrieval.",
                file=sys.stderr,
            )
            records = _get_batch_from_mail(
                source,
                messages,
                body_limit=args.body_limit,
                timeout=args.timeout,
            )
        _print_json(records)
        return
    _print_json(
        _get_batch_from_mail(
            source,
            messages,
            body_limit=args.body_limit,
            timeout=args.timeout,
        )
    )


def command_plan_transfer(args: argparse.Namespace) -> None:
    records = _selection_records(args.selection)
    if len(records) > PUBLIC_GMAIL_BATCH_LIMIT:
        raise ValueError(
            "Gmail transfer batch size cannot exceed {} messages".format(
                PUBLIC_GMAIL_BATCH_LIMIT
            )
        )
    plan = build_message_plan(
        "gmail_inbox_to_local",
        account_source(args.account, "INBOX"),
        records,
        destination=local_destination(args.destination),
    )
    _write_plan(plan, args.output)


def command_plan_spam_transfer(args: argparse.Namespace) -> None:
    records = _selection_records(args.selection)
    if len(records) > PUBLIC_GMAIL_BATCH_LIMIT:
        raise ValueError(
            "Gmail transfer batch size cannot exceed {} messages".format(
                PUBLIC_GMAIL_BATCH_LIMIT
            )
        )
    plan = build_message_plan(
        "gmail_spam_to_local",
        account_source(args.account, args.mailbox),
        records,
        destination=local_destination(args.destination),
    )
    _write_plan(plan, args.output)


def command_plan_local_move(args: argparse.Namespace) -> None:
    plan = build_message_plan(
        "move_local",
        local_source(args.source),
        _selection_records(args.selection),
        destination=local_destination(args.destination),
    )
    _write_plan(plan, args.output)


def command_plan_set_read(args: argparse.Namespace) -> None:
    plan = build_message_plan(
        "set_read",
        _source_from_args(args),
        _selection_records(args.selection),
        target_read=args.state == "read",
    )
    _write_plan(plan, args.output)


def command_plan_create_mailbox(args: argparse.Namespace) -> None:
    _write_plan(build_create_mailbox_plan(args.destination), args.output)


def command_inspect_plan(args: argparse.Namespace) -> None:
    plan = read_json(args.plan)
    validate_plan(plan)
    _print_json(plan)


def command_verify(args: argparse.Namespace) -> None:
    plan = read_json(args.plan)
    validate_plan(plan)
    _print_json(verify_messages(MailRunner(APPLESCRIPT_DIR, args.timeout), plan))


def command_reconcile(args: argparse.Namespace) -> None:
    plan = read_json(args.plan)
    validate_plan(plan)
    _print_json(
        reconcile_gmail_transfer(
            MailRunner(APPLESCRIPT_DIR, args.timeout),
            plan,
            audit_path=args.audit,
        )
    )


def command_probe_copy(args: argparse.Namespace) -> None:
    plan = read_json(args.plan)
    validate_plan(plan)
    _print_json(
        probe_account_to_local_copy(
            MailRunner(APPLESCRIPT_DIR, args.timeout), plan
        )
    )


def command_apply(args: argparse.Namespace) -> None:
    plan = read_json(args.plan)
    require_allowed_destination(plan, args.allow_destination)
    if not args.execute:
        _print_json(
            {
                "status": "dry_run",
                "action": plan["action"],
                "plan_hash": plan["plan_hash"],
                "message_count": len(plan.get("messages", [])),
                "destination": plan.get("destination"),
            }
        )
        return
    if args.audit is None:
        raise ValueError("--audit is required with --execute")
    runner = MailRunner(APPLESCRIPT_DIR, args.timeout)
    action = plan["action"]
    try:
        if action == "move_local":
            result = apply_local_move(
                runner,
                plan,
                allowed_destinations=args.allow_destination,
                audit_path=args.audit,
            )
        elif action == "set_read":
            result = apply_set_read(runner, plan, audit_path=args.audit)
        elif action == "create_local_mailbox":
            result = apply_create_mailbox(
                runner,
                plan,
                allowed_destinations=args.allow_destination,
                audit_path=args.audit,
            )
        elif action in ("gmail_inbox_to_local", "gmail_spam_to_local"):
            if args.token is None or not args.expected_account:
                raise ValueError(
                    "--token and --expected-account are required for Gmail transfer"
                )
            handler = (
                apply_gmail_inbox_to_local
                if action == "gmail_inbox_to_local"
                else apply_gmail_spam_to_local
            )
            result = handler(
                runner,
                GmailClient(TokenStore(args.token)),
                plan,
                expected_account=args.expected_account,
                allowed_destinations=args.allow_destination,
                audit_path=args.audit,
            )
        else:
            raise ValueError("Unsupported plan action")
    except Exception as error:
        failure_status = (
            "mutation_state_unknown"
            if isinstance(error, GmailMutationStateUnknown)
            else "operation_failed"
        )
        append_audit_event(
            args.audit,
            {
                "status": failure_status,
                "action": action,
                "plan_hash": plan["plan_hash"],
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise
    _print_json(result)


def command_authorize(args: argparse.Namespace) -> None:
    authorize_desktop(args.client_secrets, args.token, timeout=args.auth_timeout)


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--local", help="Fully qualified On My Mac path")
    group.add_argument("--account", help="Exact Mail account name")
    parser.add_argument("--mailbox", default="INBOX", help="Account mailbox name")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apple-mail",
        description="Generic, script-driven Apple Mail operations",
    )
    parser.add_argument("--timeout", type=int, default=120)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover")
    discover.set_defaults(handler=command_discover)

    list_parser = subparsers.add_parser("list")
    _add_source_arguments(list_parser)
    list_parser.add_argument("--start", type=int, default=1)
    list_parser.add_argument("--limit", type=int, default=50)
    list_parser.set_defaults(handler=command_list)

    get_parser = subparsers.add_parser("get")
    _add_source_arguments(get_parser)
    get_parser.add_argument("--mail-id", type=int, required=True)
    get_parser.add_argument("--message-id", required=True)
    get_parser.add_argument("--body-limit", type=int, default=50000)
    get_parser.set_defaults(handler=command_get)

    get_batch = subparsers.add_parser("get-batch")
    _add_source_arguments(get_batch)
    get_batch.add_argument("--selection", type=Path, required=True)
    get_batch.add_argument("--body-limit", type=int, default=50000)
    get_batch.add_argument("--token", type=Path)
    get_batch.add_argument("--expected-account")
    get_batch.set_defaults(handler=command_get_batch)

    transfer = subparsers.add_parser("plan-gmail-transfer")
    transfer.add_argument("--account", required=True)
    transfer.add_argument("--destination", required=True)
    transfer.add_argument("--selection", type=Path, required=True)
    transfer.add_argument("--output", type=Path, required=True)
    transfer.set_defaults(handler=command_plan_transfer)

    spam_transfer = subparsers.add_parser(
        "plan-gmail-junk-transfer",
        aliases=["plan-gmail-spam-transfer"],
    )
    spam_transfer.add_argument("--account", required=True)
    spam_transfer.add_argument(
        "--mailbox",
        required=True,
        help="Exact Apple Mail mailbox name for Gmail Spam/Junk",
    )
    spam_transfer.add_argument("--destination", required=True)
    spam_transfer.add_argument("--selection", type=Path, required=True)
    spam_transfer.add_argument("--output", type=Path, required=True)
    spam_transfer.set_defaults(handler=command_plan_spam_transfer)

    local_move = subparsers.add_parser("plan-local-move")
    local_move.add_argument("--source", required=True)
    local_move.add_argument("--destination", required=True)
    local_move.add_argument("--selection", type=Path, required=True)
    local_move.add_argument("--output", type=Path, required=True)
    local_move.set_defaults(handler=command_plan_local_move)

    set_read = subparsers.add_parser("plan-set-read")
    _add_source_arguments(set_read)
    set_read.add_argument("--state", choices=("read", "unread"), required=True)
    set_read.add_argument("--selection", type=Path, required=True)
    set_read.add_argument("--output", type=Path, required=True)
    set_read.set_defaults(handler=command_plan_set_read)

    create = subparsers.add_parser("plan-create-mailbox")
    create.add_argument("--destination", required=True)
    create.add_argument("--output", type=Path, required=True)
    create.set_defaults(handler=command_plan_create_mailbox)

    inspect = subparsers.add_parser("inspect-plan")
    inspect.add_argument("--plan", type=Path, required=True)
    inspect.set_defaults(handler=command_inspect_plan)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--plan", type=Path, required=True)
    verify.set_defaults(handler=command_verify)

    reconcile = subparsers.add_parser("reconcile")
    reconcile.add_argument("--plan", type=Path, required=True)
    reconcile.add_argument("--audit", type=Path, required=True)
    reconcile.set_defaults(handler=command_reconcile)

    probe_copy = subparsers.add_parser("probe-copy")
    probe_copy.add_argument("--plan", type=Path, required=True)
    probe_copy.set_defaults(handler=command_probe_copy)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--plan", type=Path, required=True)
    apply_parser.add_argument(
        "--allow-destination",
        action="append",
        default=[],
        help="Exact local destination; repeat to allow more than one",
    )
    apply_parser.add_argument("--audit", type=Path)
    apply_parser.add_argument("--token", type=Path)
    apply_parser.add_argument("--expected-account")
    apply_parser.add_argument("--execute", action="store_true")
    apply_parser.set_defaults(handler=command_apply)

    authorize = subparsers.add_parser("authorize")
    authorize.add_argument("--client-secrets", type=Path, required=True)
    authorize.add_argument("--token", type=Path, required=True)
    authorize.add_argument("--auth-timeout", type=int, default=300)
    authorize.set_defaults(handler=command_authorize)
    return parser


def main(argv: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except Exception as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1
    return 0
