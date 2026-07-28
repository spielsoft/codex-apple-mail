import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class OAuthError(RuntimeError):
    pass


def load_client_secrets(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    installed = document.get("installed")
    if not isinstance(installed, dict):
        raise OAuthError("OAuth credential must be a Desktop app ('installed') client")
    if not installed.get("client_id"):
        raise OAuthError("OAuth credential is missing client_id")
    return installed


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _post_form(url: str, values: Dict[str, str]) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(values).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise OAuthError("OAuth endpoint returned HTTP {}: {}".format(error.code, body))
    except urllib.error.URLError as error:
        raise OAuthError("OAuth network error: {}".format(error.reason))


def _write_private_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    result: Dict[str, str] = {}
    expected_state = ""

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        if state != self.expected_state:
            type(self).result = {"error": "OAuth state mismatch"}
            status = 400
        elif query.get("error"):
            type(self).result = {"error": query["error"][0]}
            status = 400
        elif not query.get("code"):
            type(self).result = {"error": "OAuth callback did not include a code"}
            status = 400
        else:
            type(self).result = {"code": query["code"][0]}
            status = 200
        body = (
            b"Authorization received. You may close this browser tab."
            if status == 200
            else b"Authorization failed. Return to the terminal for details."
        )
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def authorize_desktop(
    client_secrets_path: Path, token_path: Path, timeout: int = 300
) -> str:
    if token_path.exists():
        raise OAuthError(
            "Token path already exists; choose a new path or remove it deliberately"
        )
    client = load_client_secrets(client_secrets_path)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())

    handler = type("OAuthCallbackHandler", (_OAuthCallbackHandler,), {})
    handler.expected_state = state
    handler.result = {}
    server = HTTPServer(("127.0.0.1", 0), handler)
    server.timeout = 1
    redirect_uri = "http://127.0.0.1:{}/".format(server.server_port)
    authorization_uri = client.get("auth_uri", DEFAULT_AUTH_URI)
    query = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_MODIFY_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorization_url = authorization_uri + "?" + urllib.parse.urlencode(query)
    print("Open this URL in your browser and authorize the Gmail account:")
    print(authorization_url)
    print("Waiting for the local OAuth callback on 127.0.0.1...")

    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline and not handler.result:
            server.handle_request()
    finally:
        server.server_close()
    if not handler.result:
        raise OAuthError("Timed out waiting for OAuth authorization")
    if handler.result.get("error"):
        raise OAuthError(handler.result["error"])

    token_values = {
        "client_id": client["client_id"],
        "code": handler.result["code"],
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if client.get("client_secret"):
        token_values["client_secret"] = client["client_secret"]
    token_uri = client.get("token_uri", DEFAULT_TOKEN_URI)
    token_response = _post_form(token_uri, token_values)
    if not token_response.get("access_token"):
        raise OAuthError("OAuth token response is missing access_token")
    if not token_response.get("refresh_token"):
        raise OAuthError(
            "OAuth token response is missing refresh_token; revoke prior consent and retry"
        )
    token_document = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response["refresh_token"],
        "expires_at": int(time.time()) + int(token_response.get("expires_in", 3600)),
        "scope": token_response.get("scope", GMAIL_MODIFY_SCOPE),
        "token_type": token_response.get("token_type", "Bearer"),
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret", ""),
        "token_uri": token_uri,
    }
    _write_private_json(token_path, token_document)
    return authorization_url


class TokenStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
        required = ("access_token", "refresh_token", "client_id", "token_uri")
        for field in required:
            if not document.get(field):
                raise OAuthError("Token file is missing {}".format(field))
        granted_scopes = set(str(document.get("scope", "")).split())
        if GMAIL_MODIFY_SCOPE not in granted_scopes:
            raise OAuthError("Token does not grant the required gmail.modify scope")
        return document

    def access_token(self) -> str:
        document = self.load()
        if int(document.get("expires_at", 0)) > int(time.time()) + 60:
            return str(document["access_token"])
        values = {
            "client_id": str(document["client_id"]),
            "refresh_token": str(document["refresh_token"]),
            "grant_type": "refresh_token",
        }
        if document.get("client_secret"):
            values["client_secret"] = str(document["client_secret"])
        response = _post_form(str(document["token_uri"]), values)
        if not response.get("access_token"):
            raise OAuthError("Refresh response is missing access_token")
        document["access_token"] = response["access_token"]
        document["expires_at"] = int(time.time()) + int(response.get("expires_in", 3600))
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        _write_private_json(temporary, document)
        os.replace(str(temporary), str(self.path))
        os.chmod(str(self.path), 0o600)
        return str(document["access_token"])
