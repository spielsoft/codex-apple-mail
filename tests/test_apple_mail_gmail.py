import base64
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "skills" / "apple-mail" / "scripts")
)

from apple_mail.gmail import (
    GmailBodyUnavailable,
    GmailClient,
    GmailError,
    corroborates_plan_item,
    corroboration_mismatches,
    get_message_records_parallel,
    resolve_messages_parallel,
)
from apple_mail.gmail_content import attachment_count, message_body


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
    def test_resolution_error_identifies_item_with_no_search_candidate(self):
        class MissingReferenceClient:
            def list_by_rfc_message_id(self, message_id):
                if message_id == "stable-2@example.com":
                    return []
                return [{"id": "gmail-1"}]

            def get_metadata(self, gmail_id):
                return {
                    "id": gmail_id,
                    "payload": {
                        "headers": [
                            {
                                "name": "Message-ID",
                                "value": "<stable-1@example.com>",
                            },
                            {"name": "Subject", "value": "Example 1"},
                            {
                                "name": "From",
                                "value": "Sender <sender@example.com>",
                            },
                        ]
                    },
                }

        items = [
            {
                "message_id": "stable-1@example.com",
                "subject": "Example 1",
                "sender": "Sender <sender@example.com>",
                "received_at": "2018-03-07T12:00:00",
            },
            {
                "message_id": "stable-2@example.com",
                "subject": "Example 2",
                "sender": "Sender <sender@example.com>",
                "received_at": "2018-03-07T12:00:00",
            },
        ]

        with self.assertRaisesRegex(
            GmailError,
            r"planned item 2: stage=reference_lookup; "
            r"observed_count=0; expected_count=1$",
        ) as caught:
            resolve_messages_parallel(MissingReferenceClient(), items)

        self.assertNotIn("stable-2@example.com", str(caught.exception))
        self.assertNotIn("Example 2", str(caught.exception))

    def test_resolution_error_names_single_candidate_mismatched_fields(self):
        class NonmatchingMetadataClient:
            def list_by_rfc_message_id(self, message_id):
                return [{"id": "gmail-a"}]

            def get_metadata(self, gmail_id):
                return {
                    "id": gmail_id,
                    "internalDate": "1",
                    "payload": {
                        "headers": [
                            {
                                "name": "Message-ID",
                                "value": "<different@example.com>",
                            },
                            {"name": "Subject", "value": "Different"},
                            {
                                "name": "From",
                                "value": "Other <other@example.com>",
                            },
                        ]
                    },
                }

        item = {
            "message_id": "stable@example.com",
            "subject": "Example",
            "sender": "Sender <sender@example.com>",
            "received_at": "2018-03-07T12:00:00",
        }

        with self.assertRaisesRegex(
            GmailError,
            r"planned item 1: stage=metadata_corroboration; "
            r"observed_count=0; expected_count=1; candidate_count=1; "
            r"mismatched_fields=message_id,subject,sender,received_date$",
        ) as caught:
            resolve_messages_parallel(NonmatchingMetadataClient(), [item])

        self.assertNotIn("stable@example.com", str(caught.exception))
        self.assertNotIn("Example", str(caught.exception))
        self.assertNotIn("sender@example.com", str(caught.exception))

    def test_boolean_corroboration_wrapper_uses_canonical_field_details(self):
        item = {
            "message_id": "stable@example.com",
            "subject": "Example",
            "sender": "Sender <sender@example.com>",
            "received_at": "2018-03-07T12:00:00",
            "read": True,
        }
        candidate = {
            "labelIds": ["UNREAD"],
            "payload": {
                "headers": [
                    {
                        "name": "Message-ID",
                        "value": "<stable@example.com>",
                    },
                    {"name": "Subject", "value": "Different"},
                    {
                        "name": "From",
                        "value": "Sender <sender@example.com>",
                    },
                ]
            },
        }

        self.assertEqual(
            corroboration_mismatches(candidate, item, require_read=True),
            ["subject", "read_state"],
        )
        self.assertFalse(
            corroborates_plan_item(candidate, item, require_read=True)
        )

    def test_received_time_accepts_adjacent_date_within_24_hours(self):
        expected = datetime(2018, 3, 7, 23, 30)
        candidate = {
            "internalDate": str(
                int((expected + timedelta(minutes=45)).timestamp() * 1000)
            ),
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
        item = {
            "message_id": "stable@example.com",
            "subject": "Example",
            "sender": "Sender <sender@example.com>",
            "received_at": expected.isoformat(),
        }

        self.assertEqual(corroboration_mismatches(candidate, item), [])

    def test_received_time_rejects_more_than_24_hours(self):
        expected = datetime(2018, 3, 7, 12, 0)
        candidate_time = expected + timedelta(hours=24, seconds=1)
        candidate = {
            "internalDate": str(int(candidate_time.timestamp() * 1000)),
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
        item = {
            "message_id": "stable@example.com",
            "subject": "Example",
            "sender": "Sender <sender@example.com>",
            "received_at": expected.isoformat(),
        }

        self.assertEqual(
            corroboration_mismatches(candidate, item),
            ["received_date"],
        )

    def test_inline_plain_text_body_is_decoded(self):
        body = base64.urlsafe_b64encode(
            "Line one\nLine two".encode("utf-8")
        ).decode("ascii").rstrip("=")
        message = {
            "payload": {
                "mimeType": "text/plain",
                "body": {"data": body, "size": 17},
            }
        }
        self.assertEqual(message_body(message), "Line one\nLine two")

    def test_external_text_body_fails_closed(self):
        message = {
            "payload": {
                "mimeType": "text/plain",
                "body": {"attachmentId": "external-body", "size": 20},
            }
        }
        with self.assertRaisesRegex(GmailBodyUnavailable, "not available inline"):
            message_body(message)

    def test_empty_inline_data_with_positive_or_malformed_size_fails_closed(self):
        for size in (20, "not-a-size"):
            message = {
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"data": "", "size": size},
                }
            }
            with self.subTest(size=size), self.assertRaises(
                GmailBodyUnavailable
            ):
                message_body(message)

    def test_gmail_mime_attachment_count_covers_disposition_and_external_parts(self):
        message = {
            "payload": {
                "mimeType": "multipart/mixed",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": "", "size": 0},
                    },
                    {
                        "mimeType": "application/octet-stream",
                        "filename": "",
                        "headers": [
                            {
                                "name": "Content-Disposition",
                                "value": "attachment",
                            }
                        ],
                        "body": {"attachmentId": "document", "size": 100},
                    },
                    {
                        "mimeType": "image/png",
                        "filename": "",
                        "body": {"attachmentId": "inline-image", "size": 100},
                    },
                ],
            }
        }
        self.assertEqual(attachment_count(message), 2)

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
        self.assertEqual(records[0]["ATTACHMENT_COUNT_SOURCE"], "gmail_mime")

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
        with self.assertRaisesRegex(
            GmailError,
            r"planned item 1: stage=read_state_corroboration; "
            r"observed_count=0; expected_count=1; "
            r"mismatched_fields=read_state$",
        ):
            get_message_records_parallel(client, [item], body_limit=100)
        self.assertEqual(client.full_calls, 0)

    def test_full_corroboration_error_names_fields_without_values(self):
        class FullMismatchClient:
            def list_by_rfc_message_id(self, message_id):
                return [{"id": "gmail-1"}]

            def _message(self, *, subject, unread):
                return {
                    "id": "gmail-1",
                    "labelIds": ["UNREAD"] if unread else [],
                    "payload": {
                        "headers": [
                            {
                                "name": "Message-ID",
                                "value": "<stable@example.com>",
                            },
                            {"name": "Subject", "value": subject},
                            {
                                "name": "From",
                                "value": "Sender <sender@example.com>",
                            },
                        ]
                    },
                }

            def get_metadata(self, gmail_id):
                return self._message(subject="Expected subject", unread=False)

            def get_full(self, gmail_id):
                return self._message(subject="Private changed value", unread=True)

        item = {
            "mail_id": 123,
            "message_id": "stable@example.com",
            "subject": "Expected subject",
            "sender": "Sender <sender@example.com>",
            "received_at": "2018-03-07T12:00:00",
            "read": True,
        }

        with self.assertRaisesRegex(
            GmailError,
            r"planned item 1: stage=full_identity_corroboration; "
            r"observed_count=0; expected_count=1; "
            r"mismatched_fields=subject,read_state$",
        ) as caught:
            get_message_records_parallel(
                FullMismatchClient(),
                [item],
                body_limit=100,
            )

        self.assertNotIn("Expected subject", str(caught.exception))
        self.assertNotIn("Private changed value", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
