import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "skills" / "apple-mail" / "scripts")
)

from apple_mail.plans import (
    PlanError,
    account_source,
    build_create_mailbox_plan,
    build_message_plan,
    local_destination,
    local_source,
    require_allowed_destination,
    validate_plan,
    write_json,
)


MESSAGE = {
    "mail_id": 123,
    "message_id": "stable-id@example.com",
    "subject": "Example",
    "sender": "Sender <sender@example.com>",
    "received_at": "2018-03-07T12:00:00",
    "read": False,
}


class AppleMailPlanTests(unittest.TestCase):
    def test_gmail_plan_is_generic_and_hashed(self):
        plan = build_message_plan(
            "gmail_inbox_to_local",
            account_source("person@example.com"),
            [MESSAGE],
            destination=local_destination("On My Mac/Review"),
        )
        validate_plan(plan)
        self.assertEqual(plan["messages"][0]["mail_id"], 123)
        require_allowed_destination(plan, ["On My Mac/Review"])
        with self.assertRaises(PlanError):
            require_allowed_destination(plan, ["On My Mac/Other"])

    def test_gmail_spam_plan_accepts_exact_account_mailbox(self):
        plan = build_message_plan(
            "gmail_spam_to_local",
            account_source("person@example.com", "Junk"),
            [MESSAGE],
            destination=local_destination("On My Mac/Review"),
        )

        validate_plan(plan)
        self.assertEqual(plan["source"]["mailbox"], "Junk")

    def test_tampering_breaks_hash(self):
        plan = build_message_plan(
            "move_local",
            local_source("On My Mac/One"),
            [MESSAGE],
            destination=local_destination("On My Mac/Two"),
        )
        changed = copy.deepcopy(plan)
        changed["messages"][0]["subject"] = "Changed"
        with self.assertRaises(PlanError):
            validate_plan(changed)

    def test_legacy_numeric_id_fields_are_accepted_at_plan_boundary(self):
        selection = dict(MESSAGE)
        del selection["mail_id"]
        selection["current_local_id"] = "456"
        plan = build_message_plan(
            "set_read",
            account_source("person@example.com"),
            [selection],
            target_read=True,
        )
        self.assertEqual(plan["messages"][0]["mail_id"], 456)

    def test_paths_and_actions_are_constrained(self):
        with self.assertRaises(PlanError):
            local_destination("On My Mac/Trash")
        with self.assertRaises(PlanError):
            build_message_plan(
                "move_local",
                local_source("On My Mac/One"),
                [MESSAGE],
                destination=local_destination("On My Mac/One"),
            )
        with self.assertRaises(PlanError):
            build_message_plan(
                "gmail_inbox_to_local",
                account_source("person@example.com", "Archive"),
                [MESSAGE],
                destination=local_destination("On My Mac/Review"),
            )

    def test_duplicate_and_noncanonical_messages_are_rejected(self):
        with self.assertRaises(PlanError):
            build_message_plan(
                "set_read",
                account_source("person@example.com"),
                [MESSAGE, MESSAGE],
                target_read=True,
            )
        invalid_read = dict(MESSAGE)
        invalid_read["read"] = 0
        with self.assertRaises(PlanError):
            build_message_plan(
                "set_read",
                account_source("person@example.com"),
                [invalid_read],
                target_read=True,
            )

    def test_mailbox_creation_is_plan_based_and_exclusive(self):
        plan = build_create_mailbox_plan("On My Mac/New Folder")
        validate_plan(plan)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            write_json(path, plan)
            with self.assertRaises(FileExistsError):
                write_json(path, plan)


if __name__ == "__main__":
    unittest.main()
