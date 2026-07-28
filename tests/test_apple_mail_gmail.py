import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "skills" / "apple-mail" / "scripts")
)

from apple_mail.gmail import GmailClient, GmailError


class DummyTokenStore:
    def access_token(self):
        return "unused"


class RecordingClient(GmailClient):
    def __init__(self):
        super().__init__(DummyTokenStore())
        self.calls = []

    def _request(self, method, path, query=None, body=None):
        self.calls.append((method, path, query, body))
        return {"id": "abc123", "labelIds": []}


class AppleMailGmailTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
