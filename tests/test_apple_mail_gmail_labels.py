import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "skills" / "apple-mail" / "scripts")
)

from apple_mail.gmail_labels import (
    remove_inbox_labels_with_rollback,
    remove_spam_labels_with_rollback,
)


class GmailLabelConfirmationTests(unittest.TestCase):
    def test_spam_batch_retries_only_transient_metadata_reads(self):
        message_count = 49

        class TransientMetadataClient:
            def __init__(self):
                self.labels = {
                    "gmail-{}".format(index): {"SPAM", "IMPORTANT"}
                    for index in range(message_count)
                }
                self.metadata_calls = {
                    gmail_id: 0 for gmail_id in self.labels
                }

            def modify_label(
                self, gmail_id, label, *, add=False, remove=False
            ):
                if add:
                    self.labels[gmail_id].add(label)
                else:
                    self.labels[gmail_id].discard(label)
                    if label == "SPAM":
                        self.labels[gmail_id].add("INBOX")
                # Exercise the authoritative-read fallback for every item.
                return {"id": gmail_id}

            def get_metadata(self, gmail_id):
                self.metadata_calls[gmail_id] += 1
                if (
                    gmail_id == "gmail-7"
                    and self.metadata_calls[gmail_id] == 1
                ):
                    raise RuntimeError("temporary metadata failure")
                return {
                    "id": gmail_id,
                    "labelIds": sorted(self.labels[gmail_id]),
                }

        client = TransientMetadataClient()
        planned = [
            {
                "id": "gmail-{}".format(index),
                "labelIds": ["SPAM", "IMPORTANT"],
            }
            for index in range(message_count)
        ]
        with patch(
            "apple_mail.gmail_labels.time.sleep",
            return_value=None,
        ):
            changed = remove_spam_labels_with_rollback(client, planned)

        self.assertEqual(changed, [item["id"] for item in planned])
        self.assertTrue(
            all(labels == {"IMPORTANT"} for labels in client.labels.values())
        )
        self.assertEqual(client.metadata_calls["gmail-7"], 3)
        self.assertTrue(
            all(
                count == 2
                for gmail_id, count in client.metadata_calls.items()
                if gmail_id != "gmail-7"
            )
        )

    def test_authoritative_metadata_omission_means_empty_label_set(self):
        class EmptyLabelsClient:
            def __init__(self):
                self.labels = {"INBOX"}
                self.metadata_calls = 0

            def modify_inbox_label(
                self, gmail_id, *, add=False, remove=False
            ):
                if remove:
                    self.labels.discard("INBOX")
                else:
                    self.labels.add("INBOX")
                return {"id": gmail_id}

            def get_metadata(self, gmail_id):
                self.metadata_calls += 1
                return {"id": gmail_id}

        client = EmptyLabelsClient()
        changed = remove_inbox_labels_with_rollback(
            client,
            [{"id": "gmail-1", "labelIds": ["INBOX"]}],
        )

        self.assertEqual(changed, ["gmail-1"])
        self.assertEqual(client.labels, set())
        self.assertEqual(client.metadata_calls, 1)


if __name__ == "__main__":
    unittest.main()
