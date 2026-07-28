import base64
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Sequence

from .oauth import TokenStore


API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"
PERMITTED_LABEL = "INBOX"
FORBIDDEN_LABEL = "TRASH"


class GmailError(RuntimeError):
    pass


class GmailClient:
    def __init__(self, token_store: TokenStore):
        self.token_store = token_store
        self._token_lock = threading.Lock()
        self._access_token_value: Optional[str] = None

    def _access_token(self) -> str:
        if self._access_token_value is not None:
            return self._access_token_value
        with self._token_lock:
            if self._access_token_value is None:
                self._access_token_value = self.token_store.access_token()
        return self._access_token_value

    def _request(
        self,
        method: str,
        path: str,
        query: Optional[Sequence[tuple]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if method not in ("GET", "POST"):
            raise GmailError("HTTP method is not allowlisted")
        if not path.startswith("/") or ".." in path:
            raise GmailError("Unsafe Gmail API path")
        message_path = re.fullmatch(r"/messages/([A-Za-z0-9_-]+)", path)
        modify_path = re.fullmatch(
            r"/messages/([A-Za-z0-9_-]+)/modify", path
        )
        route_is_allowed = (
            (method == "GET" and path in ("/profile", "/messages"))
            or (method == "GET" and message_path is not None)
            or (method == "POST" and modify_path is not None)
        )
        if not route_is_allowed:
            raise GmailError("Gmail API endpoint is not allowlisted")
        if method == "POST":
            permitted_bodies = (
                {"addLabelIds": [PERMITTED_LABEL], "removeLabelIds": []},
                {"addLabelIds": [], "removeLabelIds": [PERMITTED_LABEL]},
            )
            if body not in permitted_bodies:
                raise GmailError("Gmail label mutation is not allowlisted")
        url = API_ROOT + path
        if query:
            url += "?" + urllib.parse.urlencode(list(query), doseq=True)
        headers = {
            "Authorization": "Bearer {}".format(self._access_token()),
            "Accept": "application/json",
        }
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                return json.loads(payload.decode("utf-8")) if payload else {}
        except urllib.error.HTTPError as error:
            payload = error.read().decode("utf-8", errors="replace")
            raise GmailError(
                "Gmail API returned HTTP {}: {}".format(error.code, payload)
            )
        except urllib.error.URLError as error:
            raise GmailError("Gmail API network error: {}".format(error.reason))

    def profile(self) -> Dict[str, Any]:
        return self._request("GET", "/profile")

    def list_by_rfc_message_id(self, message_id: str) -> List[Dict[str, str]]:
        query_value = "rfc822msgid:{}".format(message_id.strip("<>"))
        response = self._request(
            "GET",
            "/messages",
            query=(("q", query_value), ("maxResults", "10")),
        )
        return list(response.get("messages", []))

    def get_metadata(self, gmail_message_id: str) -> Dict[str, Any]:
        query = [
            ("format", "metadata"),
            ("metadataHeaders", "Message-ID"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "Date"),
        ]
        return self._request("GET", "/messages/{}".format(gmail_message_id), query)

    def get_full(self, gmail_message_id: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/messages/{}".format(gmail_message_id),
            (("format", "full"),),
        )

    def modify_inbox_label(
        self, gmail_message_id: str, *, add: bool = False, remove: bool = False
    ) -> Dict[str, Any]:
        if add == remove:
            raise GmailError("Exactly one of add or remove must be true")
        body = {
            "addLabelIds": [PERMITTED_LABEL] if add else [],
            "removeLabelIds": [PERMITTED_LABEL] if remove else [],
        }
        return self._request(
            "POST", "/messages/{}/modify".format(gmail_message_id), body=body
        )


def header_map(message: Dict[str, Any]) -> Dict[str, str]:
    headers = message.get("payload", {}).get("headers", [])
    return {
        str(header.get("name", "")).lower(): str(header.get("value", ""))
        for header in headers
    }


def corroborates_plan_item(
    message: Dict[str, Any],
    item: Dict[str, Any],
    *,
    require_read: bool = False,
) -> bool:
    headers = header_map(message)
    expected_id = str(item["message_id"]).strip("<>").lower()
    actual_id = headers.get("message-id", "").strip("<>").lower()
    if actual_id != expected_id:
        return False
    if headers.get("subject", "") != item["subject"]:
        return False
    expected_sender = parseaddr(str(item.get("sender", "")))[1].lower()
    actual_sender = parseaddr(headers.get("from", ""))[1].lower()
    if expected_sender and actual_sender != expected_sender:
        return False
    internal_date = message.get("internalDate")
    if internal_date:
        actual_local_date = datetime.fromtimestamp(int(internal_date) / 1000).date()
        expected_date = datetime.fromisoformat(str(item["received_at"])).date()
        if actual_local_date != expected_date:
            return False
    if require_read:
        actual_read = "UNREAD" not in set(message.get("labelIds", []))
        if actual_read != bool(item["read"]):
            return False
    return True


def resolve_unique_message(
    client: GmailClient, item: Dict[str, Any]
) -> Dict[str, Any]:
    references = client.list_by_rfc_message_id(str(item["message_id"]))
    matches: List[Dict[str, Any]] = []
    for reference in references:
        message = client.get_metadata(reference["id"])
        if corroborates_plan_item(message, item):
            matches.append(message)
    if len(matches) != 1:
        raise GmailError(
            "Expected one corroborated Gmail message, found {}".format(len(matches))
        )
    return matches[0]


def resolve_messages_parallel(
    client: GmailClient,
    items: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not items or len(items) > 10:
        raise GmailError("Gmail batch size must be between 1 and 10 messages")
    with ThreadPoolExecutor(max_workers=len(items)) as executor:
        return list(
            executor.map(
                lambda item: resolve_unique_message(client, item),
                items,
            )
        )


def _decode_body_data(data: str) -> str:
    if not data:
        return ""
    padded = data + ("=" * (-len(data) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise GmailError("Gmail message body is not valid base64url") from error
    return raw.decode("utf-8", errors="replace")


def _walk_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    output = [payload]
    for part in payload.get("parts", []) or []:
        if isinstance(part, dict):
            output.extend(_walk_payload(part))
    return output


class _PlainTextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: List[str] = []

    def handle_data(self, data: str) -> None:
        self.fragments.append(data)

    def handle_starttag(
        self, tag: str, attrs: List[tuple]
    ) -> None:
        if tag.casefold() in ("br", "div", "li", "p", "tr"):
            self.fragments.append("\n")

    def text(self) -> str:
        return "".join(self.fragments).strip()


def message_body(message: Dict[str, Any]) -> str:
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        return ""
    parts = _walk_payload(payload)
    plain = [
        _decode_body_data(str(part.get("body", {}).get("data", "")))
        for part in parts
        if part.get("mimeType") == "text/plain"
        and not str(part.get("filename", ""))
        and part.get("body", {}).get("data")
    ]
    if plain:
        return "\n".join(value for value in plain if value)
    html_parts = [
        _decode_body_data(str(part.get("body", {}).get("data", "")))
        for part in parts
        if part.get("mimeType") == "text/html"
        and not str(part.get("filename", ""))
        and part.get("body", {}).get("data")
    ]
    parser = _PlainTextHTMLParser()
    for html_value in html_parts:
        parser.feed(html_value)
        parser.fragments.append("\n")
    return parser.text()


def attachment_count(message: Dict[str, Any]) -> int:
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        return 0
    return sum(
        bool(str(part.get("filename", "")))
        for part in _walk_payload(payload)
    )


def get_message_records_parallel(
    client: GmailClient,
    items: Sequence[Dict[str, Any]],
    *,
    body_limit: int,
) -> List[Dict[str, str]]:
    if body_limit < 0 or body_limit > 100000:
        raise GmailError("Body limit is outside the supported range")
    metadata = resolve_messages_parallel(client, items)
    for message, item in zip(metadata, items):
        if not corroborates_plan_item(message, item, require_read=True):
            raise GmailError("Gmail read identity corroboration failed")
    gmail_ids = [str(message["id"]) for message in metadata]
    with ThreadPoolExecutor(max_workers=len(gmail_ids)) as executor:
        full_messages = list(executor.map(client.get_full, gmail_ids))
    records: List[Dict[str, str]] = []
    for full_message, item, gmail_id in zip(full_messages, items, gmail_ids):
        if str(full_message.get("id", "")) != gmail_id:
            raise GmailError("Gmail full-message response ID changed")
        if not corroborates_plan_item(full_message, item, require_read=True):
            raise GmailError("Gmail full-message identity corroboration failed")
        body = message_body(full_message)
        truncated = len(body) > body_limit
        if truncated:
            body = body[:body_limit]
        headers = header_map(full_message)
        records.append(
            {
                "TYPE": "MESSAGE",
                "MAIL_ID": str(item["mail_id"]),
                "MESSAGE_ID": headers.get("message-id", ""),
                "SUBJECT": headers.get("subject", ""),
                "SENDER": headers.get("from", ""),
                "READ": "true"
                if "UNREAD" not in set(full_message.get("labelIds", []))
                else "false",
                "ATTACHMENT_COUNT": str(attachment_count(full_message)),
                "BODY_TRUNCATED": "true" if truncated else "false",
                "BODY": body,
            }
        )
    return records


def validate_archived_labels(message: Dict[str, Any]) -> None:
    labels = set(message.get("labelIds", []))
    if PERMITTED_LABEL in labels:
        raise GmailError("INBOX label is still present")
    if FORBIDDEN_LABEL in labels:
        raise GmailError("TRASH label appeared unexpectedly")
