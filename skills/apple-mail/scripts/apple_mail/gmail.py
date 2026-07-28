import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.utils import parseaddr
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
            "Authorization": "Bearer {}".format(self.token_store.access_token()),
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


def corroborates_plan_item(message: Dict[str, Any], item: Dict[str, Any]) -> bool:
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
            "Expected one corroborated Gmail message for {!r}, found {}".format(
                item["subject"], len(matches)
            )
        )
    return matches[0]


def validate_archived_labels(message: Dict[str, Any]) -> None:
    labels = set(message.get("labelIds", []))
    if PERMITTED_LABEL in labels:
        raise GmailError("INBOX label is still present")
    if FORBIDDEN_LABEL in labels:
        raise GmailError("TRASH label appeared unexpectedly")
