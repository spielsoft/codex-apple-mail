import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "skills" / "apple-mail" / "scripts")
)

from apple_mail.operations import (
    OperationError,
    _remove_inbox_labels_parallel,
    apply_create_mailbox,
    apply_gmail_inbox_to_local,
    apply_local_move,
    apply_set_read,
    probe_account_to_local_copy,
    verify_messages,
)
from apple_mail.plans import (
    account_source,
    build_create_mailbox_plan,
    build_message_plan,
    local_destination,
    local_source,
)


MESSAGE = {
    "mail_id": 123,
    "message_id": "stable-id@example.com",
    "subject": "Example",
    "sender": "Sender <sender@example.com>",
    "received_at": "2018-03-07T12:00:00",
    "read": False,
}


def verification(source_count="1", source_read="false", destination_count="0"):
    source_matches = "true" if source_count == "1" else "false"
    return [
        {
            "MAIL_ID": "123",
            "MESSAGE_ID": "stable-id@example.com",
            "SOURCE_ID_COUNT": source_count,
            "SOURCE_BULK_COUNT": "1" if source_count == "1" else "0",
            "SOURCE_IDENTITY": source_matches,
            "SOURCE_MESSAGE_ID_MATCH": source_matches,
            "SOURCE_SUBJECT_MATCH": source_matches,
            "SOURCE_SENDER_MATCH": source_matches,
            "SOURCE_RECEIVED_AT_MATCH": source_matches,
            "SOURCE_READ": source_read if source_count == "1" else "",
            "DESTINATION_COUNT": destination_count,
            "DESTINATION_READ": "false" if destination_count == "1" else "",
        }
    ]


def copy_barrier(destination_count="1", identity="true"):
    return [
        {
            "MAIL_ID": "123",
            "STATUS": "COPIED",
            "DESTINATION_COUNT": destination_count,
            "DESTINATION_READ": "false" if destination_count == "1" else "",
            "DESTINATION_IDENTITY": identity,
            "BARRIER_ATTEMPTS": "2",
        }
    ]


class SequencedRunner:
    def __init__(self, verifications=None, script_results=None):
        self.verifications = list(verifications or [])
        self.script_results = dict(script_results or {})
        self.calls = []

    def run_tsv(self, script, arguments=()):
        self.calls.append((script, list(arguments)))
        if script == "verify_messages.applescript":
            return self.verifications.pop(0)
        return self.script_results.get(script, [{"STATUS": "OK"}])

    def run_raw(self, script, arguments=()):
        self.calls.append((script, list(arguments)))
        return "OK"


class FakeGmailClient:
    def __init__(self):
        self.modifications = []

    def profile(self):
        return {"emailAddress": "person@example.com"}

    def list_by_rfc_message_id(self, message_id):
        return [{"id": "gmail-1"}]

    def get_metadata(self, gmail_id):
        return {
            "id": gmail_id,
            "labelIds": ["INBOX", "IMPORTANT"],
            "payload": {
                "headers": [
                    {"name": "Message-ID", "value": "<stable-id@example.com>"},
                    {"name": "Subject", "value": "Example"},
                    {
                        "name": "From",
                        "value": "Sender <sender@example.com>",
                    },
                ]
            },
        }

    def modify_inbox_label(self, gmail_id, *, add=False, remove=False):
        self.modifications.append((gmail_id, add, remove))
        labels = ["INBOX"] if add else ["IMPORTANT"]
        return {"id": gmail_id, "labelIds": labels}


class AppleMailOperationTests(unittest.TestCase):
    def test_multi_message_verification_uses_six_argument_groups(self):
        messages = []
        for index in range(9):
            message = dict(MESSAGE)
            message["mail_id"] = 1000 + index
            message["message_id"] = "stable-{}@example.com".format(index)
            message["subject"] = "Example {}".format(index)
            messages.append(message)
        plan = build_message_plan(
            "gmail_inbox_to_local",
            account_source("person@example.com"),
            messages,
            destination=local_destination("On My Mac/Review"),
        )
        runner = SequencedRunner([[]])

        verify_messages(runner, plan)

        script, arguments = runner.calls[0]
        self.assertEqual(script, "verify_messages.applescript")
        self.assertEqual(len(arguments), 5 + (9 * 6))
        for index, message in enumerate(messages):
            group_start = 5 + (index * 6)
            self.assertEqual(arguments[group_start], str(message["mail_id"]))
            self.assertEqual(
                arguments[group_start + 1], message["message_id"]
            )
            self.assertEqual(arguments[group_start + 2], message["subject"])
            self.assertEqual(arguments[group_start + 5], "false")

    def test_copy_probe_uses_exact_copy_script_without_apply_mode(self):
        plan = build_message_plan(
            "gmail_inbox_to_local",
            account_source("person@example.com"),
            [MESSAGE],
            destination=local_destination("On My Mac/Review"),
        )
        runner = SequencedRunner(
            script_results={
                "copy_account_to_local.applescript": [
                    {
                        "MODE": "probe",
                        "ITEM_COUNT": "1",
                        "COPY_COUNT": "1",
                        "REUSED_COUNT": "0",
                        "MISSING_COPY_COUNT": "1",
                        "SOURCE_SELECTOR_COUNT": "1",
                        "READY": "true",
                    }
                ]
            }
        )

        result = probe_account_to_local_copy(runner, plan)

        self.assertEqual(result["READY"], "true")
        script, arguments = runner.calls[0]
        self.assertEqual(script, "copy_account_to_local.applescript")
        self.assertEqual(arguments[0], "probe")
        self.assertEqual(len(arguments), 4 + 6)
        self.assertEqual(arguments[4], str(MESSAGE["mail_id"]))

    def test_stale_or_mismatched_numeric_id_stops_before_mutation(self):
        plan = build_message_plan(
            "move_local",
            local_source("On My Mac/One"),
            [MESSAGE],
            destination=local_destination("On My Mac/Two"),
        )
        mismatch = verification()
        mismatch[0]["SOURCE_IDENTITY"] = "false"
        runner = SequencedRunner([mismatch])
        with self.assertRaises(OperationError):
            apply_local_move(
                runner, plan, allowed_destinations=["On My Mac/Two"]
            )
        self.assertNotIn(
            "move_local_messages.applescript",
            [call[0] for call in runner.calls],
        )

    def test_preflight_diagnostic_names_only_item_and_mismatched_fields(self):
        plan = build_message_plan(
            "move_local",
            local_source("On My Mac/One"),
            [MESSAGE],
            destination=local_destination("On My Mac/Two"),
        )
        mismatch = verification()
        mismatch[0]["SOURCE_IDENTITY"] = "false"
        mismatch[0]["SOURCE_SENDER_MATCH"] = "false"
        runner = SequencedRunner([mismatch])
        with self.assertRaisesRegex(
            OperationError,
            r"Local source preflight failed: item 1 \(sender\)",
        ) as raised:
            apply_local_move(
                runner, plan, allowed_destinations=["On My Mac/Two"]
            )
        self.assertNotIn(MESSAGE["subject"], str(raised.exception))
        self.assertNotIn(MESSAGE["sender"], str(raised.exception))
        self.assertNotIn(MESSAGE["message_id"], str(raised.exception))

    def test_bulk_selector_count_mismatch_stops_before_mutation(self):
        plan = build_message_plan(
            "move_local",
            local_source("On My Mac/One"),
            [MESSAGE],
            destination=local_destination("On My Mac/Two"),
        )
        mismatch = verification()
        mismatch[0]["SOURCE_BULK_COUNT"] = "0"
        runner = SequencedRunner([mismatch])
        with self.assertRaisesRegex(
            OperationError,
            r"Local source preflight failed: bulk_selector_count",
        ):
            apply_local_move(
                runner, plan, allowed_destinations=["On My Mac/Two"]
            )
        self.assertNotIn(
            "move_local_messages.applescript",
            [call[0] for call in runner.calls],
        )

    def test_local_move_is_one_bulk_call_with_batch_verification(self):
        plan = build_message_plan(
            "move_local",
            local_source("On My Mac/One"),
            [MESSAGE],
            destination=local_destination("On My Mac/Two"),
        )
        runner = SequencedRunner(
            [verification(), verification(source_count="0", destination_count="1")]
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = apply_local_move(
                runner,
                plan,
                allowed_destinations=["On My Mac/Two"],
                audit_path=Path(temporary) / "audit.jsonl",
            )
        self.assertEqual(result["status"], "complete")
        scripts = [call[0] for call in runner.calls]
        self.assertEqual(scripts.count("move_local_messages.applescript"), 1)
        self.assertEqual(scripts.count("verify_messages.applescript"), 2)

    def test_set_read_uses_a_plan_and_verifies_target_state(self):
        plan = build_message_plan(
            "set_read",
            account_source("person@example.com"),
            [MESSAGE],
            target_read=True,
        )
        runner = SequencedRunner(
            [verification(), verification(source_read="true")]
        )
        result = apply_set_read(runner, plan)
        self.assertTrue(result["target_read"])

    def test_create_mailbox_is_idempotent(self):
        plan = build_create_mailbox_plan("On My Mac/New Folder")
        runner = SequencedRunner(
            script_results={
                "create_local_mailbox.applescript": [
                    {"STATUS": "EXISTS", "PATH": "On My Mac/New Folder"}
                ]
            }
        )
        result = apply_create_mailbox(
            runner, plan, allowed_destinations=["On My Mac/New Folder"]
        )
        self.assertEqual(result["mailbox_status"], "exists")

    def test_gmail_transfer_copies_once_then_changes_only_inbox_label(self):
        plan = build_message_plan(
            "gmail_inbox_to_local",
            account_source("person@example.com"),
            [MESSAGE],
            destination=local_destination("On My Mac/Review"),
        )
        runner = SequencedRunner(
            [
                verification(),
                verification(source_count="0", destination_count="1"),
            ],
            script_results={
                "copy_account_to_local.applescript": copy_barrier()
            },
        )
        client = FakeGmailClient()
        result = apply_gmail_inbox_to_local(
            runner,
            client,
            plan,
            expected_account="person@example.com",
            allowed_destinations=["On My Mac/Review"],
        )
        self.assertEqual(result["status"], "pending_mail_sync")
        self.assertEqual(result["local_copies_submitted"], 1)
        self.assertEqual(result["local_copies_reused"], 0)
        self.assertEqual(result["local_copy_barrier_attempts"], 2)
        self.assertIn("gmail_preflight", result["phase_seconds"])
        self.assertIn("gmail_label_removal", result["phase_seconds"])
        self.assertIn("transaction_total", result["phase_seconds"])
        self.assertNotIn("mail_preflight", result["phase_seconds"])
        self.assertNotIn("final_verify", result["phase_seconds"])
        self.assertEqual(client.modifications, [("gmail-1", False, True)])
        self.assertEqual(
            [call[0] for call in runner.calls].count(
                "copy_account_to_local.applescript"
            ),
            1,
        )
        copy_call = next(
            call
            for call in runner.calls
            if call[0] == "copy_account_to_local.applescript"
        )
        self.assertEqual(copy_call[1][0], "apply")

    def test_partial_copy_returns_pending_without_gmail_change(self):
        plan = build_message_plan(
            "gmail_inbox_to_local",
            account_source("person@example.com"),
            [MESSAGE],
            destination=local_destination("On My Mac/Review"),
        )
        runner = SequencedRunner(
            [verification()],
            script_results={
                "copy_account_to_local.applescript": copy_barrier(
                    destination_count="0", identity="false"
                )
            },
        )
        client = FakeGmailClient()
        result = apply_gmail_inbox_to_local(
            runner,
            client,
            plan,
            expected_account="person@example.com",
            allowed_destinations=["On My Mac/Review"],
        )
        self.assertEqual(result["status"], "pending_local_copy")
        self.assertEqual(result["local_copy_barrier_attempts"], 2)
        self.assertEqual(client.modifications, [])

    def test_gmail_transfer_defers_mail_cache_check_to_later_verify(self):
        plan = build_message_plan(
            "gmail_inbox_to_local",
            account_source("person@example.com"),
            [MESSAGE],
            destination=local_destination("On My Mac/Review"),
        )
        reused = verification(source_count="1", destination_count="1")
        reused[0]["SOURCE_IDENTITY"] = "false"
        runner = SequencedRunner(
            [verification(), reused],
            script_results={
                "copy_account_to_local.applescript": copy_barrier()
            },
        )
        result = apply_gmail_inbox_to_local(
            runner,
            FakeGmailClient(),
            plan,
            expected_account="person@example.com",
            allowed_destinations=["On My Mac/Review"],
        )
        self.assertEqual(result["status"], "pending_mail_sync")
        self.assertNotIn(
            "verify_messages.applescript",
            [call[0] for call in runner.calls],
        )

    def test_parallel_gmail_failure_rolls_back_every_confirmed_change(self):
        class PartialFailureClient:
            def __init__(self):
                self.calls = []

            def modify_inbox_label(self, gmail_id, *, add=False, remove=False):
                self.calls.append((gmail_id, add, remove))
                if remove and gmail_id == "gmail-2":
                    raise RuntimeError("bounded failure")
                return {
                    "id": gmail_id,
                    "labelIds": ["INBOX"] if add else ["IMPORTANT"],
                }

        client = PartialFailureClient()
        with self.assertRaisesRegex(RuntimeError, "bounded failure"):
            _remove_inbox_labels_parallel(
                client,
                [{"id": "gmail-1"}, {"id": "gmail-2"}, {"id": "gmail-3"}],
            )
        self.assertIn(("gmail-1", True, False), client.calls)
        self.assertIn(("gmail-3", True, False), client.calls)


if __name__ == "__main__":
    unittest.main()
