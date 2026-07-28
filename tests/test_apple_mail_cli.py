import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "apple-mail" / "scripts"))

from apple_mail.cli import (
    build_parser,
    command_apply,
    command_get_batch,
    command_plan_spam_transfer,
    command_plan_transfer,
)
from apple_mail.gmail import GmailBodyUnavailable, GmailError
from apple_mail.gmail_labels import GmailMutationStateUnknown
from apple_mail.plans import (
    account_source,
    build_message_plan,
    local_destination,
    write_json,
)


def message(index):
    return {
        "mail_id": 1000 + index,
        "message_id": "stable-{}@example.com".format(index),
        "subject": "Example {}".format(index),
        "sender": "Sender <sender@example.com>",
        "received_at": "2018-03-07T12:00:00",
        "read": bool(index % 2),
    }


class AppleMailCliTests(unittest.TestCase):
    def _args(self, selection):
        return argparse.Namespace(
            local=None,
            account="person@example.com",
            mailbox="INBOX",
            selection=selection,
            body_limit=50000,
            timeout=120,
        )

    def test_apply_parser_exposes_explicit_resume_flag(self):
        args = build_parser().parse_args(
            [
                "apply",
                "--plan",
                "plan.json",
                "--resume",
                "--execute",
            ]
        )

        self.assertTrue(args.resume)

    def test_get_batch_uses_one_runner_call_with_six_field_groups(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(
                json.dumps([message(index) for index in range(10)]),
                encoding="utf-8",
            )
            with (
                patch("apple_mail.cli.MailRunner") as runner_class,
                patch("apple_mail.cli._print_json"),
            ):
                records = [{"TYPE": "MESSAGE", "ATTACHMENT_COUNT": "0"}]
                runner_class.return_value.run_tsv.return_value = records
                command_get_batch(self._args(selection))

            runner_class.return_value.run_tsv.assert_called_once()
            script, arguments = (
                runner_class.return_value.run_tsv.call_args.args
            )
            self.assertEqual(script, "get_messages.applescript")
            self.assertEqual(len(arguments), 4 + (10 * 6))
            self.assertEqual(arguments[:4], [
                "account",
                "person@example.com",
                "INBOX",
                "50000",
            ])
            self.assertEqual(records[0]["ATTACHMENT_COUNT_SOURCE"], "apple_mail")

    def test_get_batch_accepts_fifty_messages_in_one_mail_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(
                json.dumps([message(index) for index in range(50)]),
                encoding="utf-8",
            )
            with (
                patch("apple_mail.cli.MailRunner") as runner_class,
                patch("apple_mail.cli._print_json"),
            ):
                command_get_batch(self._args(selection))

            runner_class.return_value.run_tsv.assert_called_once()
            script, arguments = runner_class.return_value.run_tsv.call_args.args
            self.assertEqual(script, "get_messages.applescript")
            self.assertEqual(len(arguments), 4 + (50 * 6))

    def test_get_batch_rejects_more_than_fifty_messages(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(
                json.dumps([message(index) for index in range(51)]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cannot exceed 50"):
                command_get_batch(self._args(selection))

    def test_transfer_plan_accepts_fifty_and_rejects_fifty_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selection = root / "selection.json"
            output = root / "plan.json"
            args = argparse.Namespace(
                account="person@example.com",
                destination="On My Mac/Review",
                selection=selection,
                output=output,
            )
            selection.write_text(
                json.dumps([message(index) for index in range(50)]),
                encoding="utf-8",
            )
            with patch("apple_mail.cli._print_json"):
                command_plan_transfer(args)
            self.assertEqual(
                len(json.loads(output.read_text(encoding="utf-8"))["messages"]),
                50,
            )

            selection.write_text(
                json.dumps([message(index) for index in range(51)]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cannot exceed 50"):
                command_plan_transfer(args)

    def test_junk_transfer_plan_preserves_exact_mailbox_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selection = root / "selection.json"
            output = root / "plan.json"
            selection.write_text(json.dumps([message(1)]), encoding="utf-8")
            args = argparse.Namespace(
                account="person@example.com",
                mailbox="Junk",
                destination="On My Mac/Review",
                selection=selection,
                output=output,
            )
            with patch("apple_mail.cli._print_json"):
                command_plan_spam_transfer(args)

            plan = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(plan["action"], "gmail_spam_to_local")
            self.assertEqual(plan["source"]["mailbox"], "Junk")

    def test_get_batch_uses_oauth_backend_without_calling_mail(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(json.dumps([message(1)]), encoding="utf-8")
            args = self._args(selection)
            args.token = Path(temporary) / "token.json"
            args.expected_account = "person@example.com"
            with (
                patch("apple_mail.cli.MailRunner") as runner_class,
                patch("apple_mail.cli.GmailClient") as client_class,
                patch(
                    "apple_mail.cli.get_message_records_parallel",
                    return_value=[{"TYPE": "MESSAGE"}],
                ) as get_records,
                patch("apple_mail.cli._print_json"),
            ):
                client_class.return_value.profile.return_value = {
                    "emailAddress": "person@example.com"
                }
                command_get_batch(args)

            runner_class.assert_not_called()
            get_records.assert_called_once()
            self.assertEqual(get_records.call_args.kwargs["body_limit"], 50000)

    def test_get_batch_oauth_backend_accepts_junk_mailbox_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(json.dumps([message(1)]), encoding="utf-8")
            args = self._args(selection)
            args.mailbox = "Junk"
            args.token = Path(temporary) / "token.json"
            args.expected_account = "person@example.com"
            with (
                patch("apple_mail.cli.MailRunner") as runner_class,
                patch("apple_mail.cli.GmailClient") as client_class,
                patch(
                    "apple_mail.cli.get_message_records_parallel",
                    return_value=[{"TYPE": "MESSAGE"}],
                ) as get_records,
                patch("apple_mail.cli._print_json"),
            ):
                client_class.return_value.profile.return_value = {
                    "emailAddress": "person@example.com"
                }
                command_get_batch(args)

            runner_class.assert_not_called()
            get_records.assert_called_once()

    def test_get_batch_falls_back_to_one_mail_batch_for_unavailable_gmail_body(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(json.dumps([message(1)]), encoding="utf-8")
            args = self._args(selection)
            args.token = Path(temporary) / "token.json"
            args.expected_account = "person@example.com"
            mail_record = {"TYPE": "MESSAGE", "ATTACHMENT_COUNT": "2"}
            with (
                patch("apple_mail.cli.GmailClient") as client_class,
                patch(
                    "apple_mail.cli.get_message_records_parallel",
                    side_effect=GmailBodyUnavailable("not inline"),
                ),
                patch("apple_mail.cli.MailRunner") as runner_class,
                patch("apple_mail.cli._print_json") as print_json,
            ):
                client_class.return_value.profile.return_value = {
                    "emailAddress": "person@example.com"
                }
                runner_class.return_value.run_tsv.return_value = [mail_record]
                command_get_batch(args)

            runner_class.return_value.run_tsv.assert_called_once()
            script, arguments = runner_class.return_value.run_tsv.call_args.args
            self.assertEqual(script, "get_messages.applescript")
            self.assertEqual(len(arguments), 10)
            self.assertEqual(
                print_json.call_args.args[0][0]["ATTACHMENT_COUNT_SOURCE"],
                "apple_mail",
            )

    def test_get_batch_does_not_hide_other_gmail_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(json.dumps([message(1)]), encoding="utf-8")
            args = self._args(selection)
            args.token = Path(temporary) / "token.json"
            args.expected_account = "person@example.com"
            with (
                patch("apple_mail.cli.GmailClient") as client_class,
                patch(
                    "apple_mail.cli.get_message_records_parallel",
                    side_effect=GmailError("network failed"),
                ),
                patch("apple_mail.cli.MailRunner") as runner_class,
                self.assertRaisesRegex(GmailError, "network failed"),
            ):
                client_class.return_value.profile.return_value = {
                    "emailAddress": "person@example.com"
                }
                command_get_batch(args)

            runner_class.assert_not_called()

    def test_unknown_gmail_mutation_state_has_distinct_audit_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            audit_path = root / "audit.jsonl"
            plan = build_message_plan(
                "gmail_inbox_to_local",
                account_source("person@example.com"),
                [message(1)],
                destination=local_destination("On My Mac/Review"),
            )
            write_json(plan_path, plan)
            args = argparse.Namespace(
                plan=plan_path,
                allow_destination=["On My Mac/Review"],
                execute=True,
                audit=audit_path,
                timeout=120,
                token=root / "token.json",
                expected_account="person@example.com",
            )
            with (
                patch("apple_mail.cli.MailRunner"),
                patch("apple_mail.cli.GmailClient"),
                patch(
                    "apple_mail.cli.apply_gmail_inbox_to_local",
                    side_effect=GmailMutationStateUnknown(
                        "Gmail mutation state is unknown"
                    ),
                ),
                self.assertRaises(GmailMutationStateUnknown),
            ):
                command_apply(args)

            audit = [
                json.loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(audit[-1]["status"], "mutation_state_unknown")


if __name__ == "__main__":
    unittest.main()
