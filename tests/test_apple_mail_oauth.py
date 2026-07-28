import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "skills" / "apple-mail" / "scripts")
)

from apple_mail.oauth import OAuthError, _write_private_json, load_client_secrets


class AppleMailOAuthTests(unittest.TestCase):
    def test_requires_desktop_client_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "credentials.json"
            path.write_text(json.dumps({"web": {"client_id": "wrong"}}))
            with self.assertRaises(OAuthError):
                load_client_secrets(path)
            path.write_text(json.dumps({"installed": {"client_id": "right"}}))
            self.assertEqual(load_client_secrets(path)["client_id"], "right")

    def test_private_json_is_exclusive_and_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "token.json"
            _write_private_json(path, {"secret": "value"})
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                _write_private_json(path, {"secret": "other"})


if __name__ == "__main__":
    unittest.main()
