import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "apple-mail" / "scripts"))

from apple_mail.cli import command_get_batch


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

    def test_get_batch_uses_one_runner_call_with_six_field_groups(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(
                json.dumps([message(index) for index in range(10)]),
                encoding="utf-8",
            )
            with patch("apple_mail.cli.MailRunner") as runner_class:
                runner_class.return_value.run_tsv.return_value = []
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

    def test_get_batch_rejects_more_than_ten_messages(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text(
                json.dumps([message(index) for index in range(11)]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cannot exceed 10"):
                command_get_batch(self._args(selection))


if __name__ == "__main__":
    unittest.main()
