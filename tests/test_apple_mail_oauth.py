import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(ROOT / "skills" / "apple-mail" / "scripts")
)

from apple_mail.oauth import (
    GMAIL_MODIFY_SCOPE,
    OAuthError,
    TokenStore,
    _write_private_json,
    load_client_secrets,
)


def _refresh_token_worker(token_path, start_event, results):
    try:
        start_event.wait()
        results.put(("ok", TokenStore(Path(token_path)).access_token()))
    except Exception as error:
        results.put(("error", "{}: {}".format(type(error).__name__, error)))


def _token_document(token_uri):
    return {
        "access_token": "expired-access-token",
        "refresh_token": "refresh-token",
        "expires_at": 0,
        "scope": GMAIL_MODIFY_SCOPE,
        "token_type": "Bearer",
        "client_id": "client-id",
        "client_secret": "",
        "token_uri": token_uri,
    }


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

    def test_refresh_uses_private_lock_and_unique_private_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "token.json"
            _write_private_json(path, _token_document("https://token.invalid"))
            observed_temporary_modes = []
            real_replace = os.replace

            def capture_replace(source, destination):
                observed_temporary_modes.append(os.stat(source).st_mode & 0o777)
                real_replace(source, destination)

            with (
                patch(
                    "apple_mail.oauth._post_form",
                    return_value={
                        "access_token": "refreshed-access-token",
                        "expires_in": 3600,
                    },
                ) as post_form,
                patch("apple_mail.oauth.os.replace", side_effect=capture_replace),
            ):
                self.assertEqual(
                    TokenStore(path).access_token(), "refreshed-access-token"
                )

            self.assertEqual(post_form.call_count, 1)
            self.assertEqual(observed_temporary_modes, [0o600])
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(
                os.stat(path.with_name(path.name + ".lock")).st_mode & 0o777,
                0o600,
            )
            self.assertEqual(list(path.parent.glob(".token.json.*.tmp")), [])

    def test_failed_atomic_replace_preserves_token_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "token.json"
            original = _token_document("https://token.invalid")
            _write_private_json(path, original)

            with (
                patch(
                    "apple_mail.oauth._post_form",
                    return_value={
                        "access_token": "refreshed-access-token",
                        "expires_in": 3600,
                    },
                ),
                patch(
                    "apple_mail.oauth.os.replace",
                    side_effect=OSError("simulated replace failure"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "simulated replace failure"):
                    TokenStore(path).access_token()

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)
            self.assertEqual(list(path.parent.glob(".token.json.*.tmp")), [])

    def test_concurrent_processes_share_one_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "token.json"
            _write_private_json(path, _token_document("https://token.invalid"))
            context = multiprocessing.get_context("fork")
            refresh_count = context.Value("i", 0)
            start_event = context.Event()
            results = context.Queue()

            def count_refresh(url, values):
                with refresh_count.get_lock():
                    refresh_count.value += 1
                time.sleep(0.25)
                return {
                    "access_token": "refreshed-access-token",
                    "expires_in": 3600,
                }

            processes = [
                context.Process(
                    target=_refresh_token_worker,
                    args=(str(path), start_event, results),
                )
                for _ in range(2)
            ]
            with patch("apple_mail.oauth._post_form", side_effect=count_refresh):
                for process in processes:
                    process.start()
                start_event.set()
                outcomes = [results.get(timeout=10) for _ in processes]
                for process in processes:
                    process.join(timeout=10)

            self.assertTrue(all(process.exitcode == 0 for process in processes))
            self.assertEqual(
                outcomes,
                [
                    ("ok", "refreshed-access-token"),
                    ("ok", "refreshed-access-token"),
                ],
            )
            self.assertEqual(refresh_count.value, 1)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(
                os.stat(path.with_name(path.name + ".lock")).st_mode & 0o777,
                0o600,
            )


if __name__ == "__main__":
    unittest.main()
