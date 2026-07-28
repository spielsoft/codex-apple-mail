import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "apple-mail" / "scripts"))

from apple_mail.cli import build_parser, command_reconcile
from apple_mail.plans import (
    account_source,
    build_message_plan,
    local_destination,
    write_json,
)
from apple_mail.reconciliation import reconcile_gmail_transfer


def message(index):
    return {
        "mail_id": 1000 + index,
        "message_id": "stable-{}@example.com".format(index),
        "subject": "Example {}".format(index),
        "sender": "Sender <sender@example.com>",
        "received_at": "2018-03-07T12:00:00",
        "read": bool(index % 2),
    }


def verification_row(item, *, source="present", destination_valid=True):
    source_present = source == "present"
    identity = "true" if source_present else "false"
    return {
        "MAIL_ID": str(item["mail_id"]),
        "MESSAGE_ID": item["message_id"],
        "SOURCE_ID_COUNT": "1" if source_present else "0",
        "SOURCE_BULK_COUNT": "",
        "SOURCE_IDENTITY": identity,
        "SOURCE_MESSAGE_ID_MATCH": identity,
        "SOURCE_SUBJECT_MATCH": identity,
        "SOURCE_SENDER_MATCH": identity,
        "SOURCE_RECEIVED_AT_MATCH": identity,
        "SOURCE_READ": (
            "true" if item["read"] else "false"
        ) if source_present else "",
        "DESTINATION_COUNT": "1" if destination_valid else "0",
        "DESTINATION_READ": (
            "true" if item["read"] else "false"
        ) if destination_valid else "",
    }


class VerificationRunner:
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error

    def run_tsv(self, script, arguments=()):
        if self.error is not None:
            raise self.error
        return self.rows


class AppleMailReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.messages = [message(1), message(2)]
        self.plan = build_message_plan(
            "gmail_inbox_to_local",
            account_source("person@example.com"),
            self.messages,
            destination=local_destination("On My Mac/Review"),
        )

    def _rows(self, sources, *, destinations=(True, True)):
        rows = [
            verification_row(
                item,
                source=source,
                destination_valid=destination_valid,
            )
            for item, source, destination_valid in zip(
                self.messages, sources, destinations
            )
        ]
        bulk_count = str(sum(source == "present" for source in sources))
        for row in rows:
            row["SOURCE_BULK_COUNT"] = bulk_count
        return rows

    def _reconcile(self, rows=None, error=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        audit_path = Path(temporary.name) / "audit.jsonl"
        result = reconcile_gmail_transfer(
            VerificationRunner(rows, error),
            self.plan,
            audit_path=audit_path,
        )
        records = [
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
        ]
        return result, records

    def test_complete_requires_every_source_absent_and_destination_valid(self):
        result, records = self._reconcile(
            self._rows(("absent", "absent"))
        )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["source_absent_count"], 2)
        self.assertEqual(result["destination_valid_count"], 2)
        self.assertEqual(records[-1]["status"], "complete")
        self.assertEqual(records[-1]["plan_hash"], self.plan["plan_hash"])

    def test_complete_classification_supports_spam_transfer_plan(self):
        self.plan = build_message_plan(
            "gmail_spam_to_local",
            account_source("person@example.com", "Junk"),
            self.messages,
            destination=local_destination("On My Mac/Review"),
        )

        result, records = self._reconcile(
            self._rows(("absent", "absent"))
        )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(records[-1]["action"], "gmail_spam_to_local")

    def test_exact_sources_remaining_are_pending_mail_sync(self):
        result, records = self._reconcile(
            self._rows(("present", "present"))
        )

        self.assertEqual(result["status"], "pending_mail_sync")
        self.assertEqual(result["source_exact_count"], 2)
        self.assertEqual(records[-1]["status"], "pending_mail_sync")

    def test_partial_cache_convergence_remains_pending(self):
        result, records = self._reconcile(
            self._rows(("absent", "present"))
        )

        self.assertEqual(result["status"], "pending_mail_sync")
        self.assertEqual(result["source_absent_count"], 1)
        self.assertEqual(result["source_exact_count"], 1)
        self.assertEqual(records[-1]["status"], "pending_mail_sync")

    def test_invalid_destination_state_is_unknown(self):
        result, records = self._reconcile(
            self._rows(
                ("absent", "present"),
                destinations=(True, False),
            )
        )

        self.assertEqual(result["status"], "mutation_state_unknown")
        self.assertIn("destination_copy_state", result["reason_codes"])
        self.assertEqual(records[-1]["status"], "mutation_state_unknown")

    def test_numeric_id_reuse_is_unknown(self):
        rows = self._rows(("present", "present"))
        rows[0]["SOURCE_IDENTITY"] = "false"
        rows[0]["SOURCE_MESSAGE_ID_MATCH"] = "false"

        result, records = self._reconcile(rows)

        self.assertEqual(result["status"], "mutation_state_unknown")
        self.assertIn("source_identity_state", result["reason_codes"])
        self.assertEqual(records[-1]["status"], "mutation_state_unknown")

    def test_unreadable_verification_is_audited_without_error_details(self):
        result, records = self._reconcile(
            error=RuntimeError("private message detail")
        )

        self.assertEqual(result["status"], "mutation_state_unknown")
        self.assertEqual(result["reason_codes"], ["verification_unavailable"])
        serialized = json.dumps(records[-1])
        self.assertNotIn("private message detail", serialized)
        self.assertNotIn(self.messages[0]["message_id"], serialized)

    def test_reconcile_command_requires_only_plan_and_audit(self):
        parsed = build_parser().parse_args(
            [
                "reconcile",
                "--plan",
                "plan.json",
                "--audit",
                "audit.jsonl",
            ]
        )

        self.assertIs(parsed.handler, command_reconcile)
        self.assertFalse(hasattr(parsed, "token"))
        self.assertFalse(hasattr(parsed, "expected_account"))

    def test_reconcile_command_prints_and_audits_terminal_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            audit_path = root / "audit.jsonl"
            write_json(plan_path, self.plan)
            args = build_parser().parse_args(
                [
                    "reconcile",
                    "--plan",
                    str(plan_path),
                    "--audit",
                    str(audit_path),
                ]
            )
            with (
                patch("apple_mail.cli.MailRunner") as runner_class,
                patch("apple_mail.cli._print_json") as print_json,
            ):
                runner_class.return_value.run_tsv.return_value = self._rows(
                    ("absent", "absent")
                )
                args.handler(args)

            self.assertEqual(print_json.call_args.args[0]["status"], "complete")
            audit = [
                json.loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(audit[-1]["status"], "complete")


if __name__ == "__main__":
    unittest.main()
