import base64
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "skills" / "apple-mail" / "scripts")
)

from apple_mail.gmail import (
    GmailClient,
    GmailError,
    get_message_records_parallel,
)


class DummyTokenStore:
    def __init__(self):
        self.calls = 0

    def access_token(self):
        self.calls += 1
        return "unused"


class RecordingClient(GmailClient):
    def __init__(self):
        super().__init__(DummyTokenStore())
        self.calls = []

    def _request(self, method, path, query=None, body=None):
        self.calls.append((method, path, query, body))
        return {"id": "abc123", "labelIds": []}


class AppleMailGmailTests(unittest.TestCase):
    def test_access_token_is_loaded_once_for_parallel_requests(self):
        store = DummyTokenStore()
        client = GmailClient(store)
        with ThreadPoolExecutor(max_workers=10) as executor:
            tokens = list(executor.map(lambda _: client._access_token(), range(10)))
        self.assertEqual(tokens, ["unused"] * 10)
        self.assertEqual(store.calls, 1)

    def test_only_inbox_label_can_change(self):
        client = RecordingClient()
        client.modify_inbox_label("abc123", remove=True)
        self.assertEqual(
            client.calls[-1][3],
            {"addLabelIds": [], "removeLabelIds": ["INBOX"]},
        )
        with self.assertRaises(GmailError):
            client.modify_inbox_label("abc123", add=True, remove=True)

    def test_unsafe_routes_are_rejected(self):
        client = GmailClient(DummyTokenStore())
        with self.assertRaises(GmailError):
            client._request("POST", "/messages/abc123/trash", body={})
        with self.assertRaises(GmailError):
            client._request("DELETE", "/messages/abc123")

    def test_parallel_batch_validates_all_metadata_before_fetching_bodies(self):
        class BatchClient:
            def __init__(self):
                self.metadata_count = 0
                self.full_calls = 0
                self.lock = threading.Lock()

            def list_by_rfc_message_id(self, message_id):
                index = message_id.split("@", 1)[0].split("-")[-1]
                return [{"id": "gmail-{}".format(index)}]

            def _message(self, gmail_id, body=None):
                index = int(gmail_id.split("-")[-1])
                encoded = ""
                if body is not None:
                    encoded = base64.urlsafe_b64encode(
                        body.encode("utf-8")
                    ).decode("ascii").rstrip("=")
                return {
                    "id": gmail_id,
                    "labelIds": ["INBOX"] + ([] if index % 2 else ["UNREAD"]),
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {
                                "name": "Message-ID",
                                "value": "<stable-{}@example.com>".format(index),
                            },
                            {
                                "name": "Subject",
                                "value": "Example {}".format(index),
                            },
                            {
                                "name": "From",
                                "value": "Sender <sender@example.com>",
                            },
                        ],
                        "body": {"data": encoded},
                    },
                }

            def get_metadata(self, gmail_id):
                with self.lock:
                    self.metadata_count += 1
                return self._message(gmail_id)

            def get_full(self, gmail_id):
                with self.lock:
                    if self.metadata_count != 10:
                        raise AssertionError("body fetched before metadata barrier")
                    self.full_calls += 1
                return self._message(
                    gmail_id,
                    "Line one\nLine two for {}".format(gmail_id),
                )

        items = [
            {
                "mail_id": 1000 + index,
                "message_id": "stable-{}@example.com".format(index),
                "subject": "Example {}".format(index),
                "sender": "Sender <sender@example.com>",
                "received_at": "2018-03-07T12:00:00",
                "read": bool(index % 2),
            }
            for index in range(10)
        ]
        client = BatchClient()
        records = get_message_records_parallel(client, items, body_limit=100000)
        self.assertEqual(client.full_calls, 10)
        self.assertEqual(
            [record["MAIL_ID"] for record in records],
            [str(item["mail_id"]) for item in items],
        )
        self.assertIn("\n", records[0]["BODY"])
        self.assertEqual(records[0]["READ"], "false")
        self.assertEqual(records[1]["READ"], "true")

    def test_read_mismatch_stops_before_any_full_body_fetch(self):
        class MismatchClient:
            def __init__(self):
                self.full_calls = 0

            def list_by_rfc_message_id(self, message_id):
                return [{"id": "gmail-1"}]

            def get_metadata(self, gmail_id):
                return {
                    "id": gmail_id,
                    "labelIds": ["INBOX", "UNREAD"],
                    "payload": {
                        "headers": [
                            {
                                "name": "Message-ID",
                                "value": "<stable@example.com>",
                            },
                            {"name": "Subject", "value": "Example"},
                            {
                                "name": "From",
                                "value": "Sender <sender@example.com>",
                            },
                        ]
                    },
                }

            def get_full(self, gmail_id):
                self.full_calls += 1
                return {}

        item = {
            "mail_id": 123,
            "message_id": "stable@example.com",
            "subject": "Example",
            "sender": "Sender <sender@example.com>",
            "received_at": "2018-03-07T12:00:00",
            "read": True,
        }
        client = MismatchClient()
        with self.assertRaisesRegex(GmailError, "read identity"):
            get_message_records_parallel(client, [item], body_limit=100)
        self.assertEqual(client.full_calls, 0)


if __name__ == "__main__":
    unittest.main()
