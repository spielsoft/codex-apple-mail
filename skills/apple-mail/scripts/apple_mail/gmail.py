import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Sequence

from .gmail_content import (
    GmailBodyUnavailable,
    attachment_count,
    message_body,
)
from .limits import GMAIL_NETWORK_WORKERS, PUBLIC_GMAIL_BATCH_LIMIT
from .oauth import TokenStore


API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"
MUTABLE_SOURCE_LABELS = frozenset({"INBOX", "SPAM"})
FORBIDDEN_LABEL = "TRASH"
# Apple Mail and Gmail can expose adjacent-day received timestamps with a
# small client/server processing skew. Keep this absolute window narrow so the
# date remains a meaningful corroborator alongside the unique RFC Message-ID.
RECEIVED_AT_TOLERANCE = timedelta(hours=25)


class GmailError(RuntimeError):
    pass


def _identity_resolution_error(
    item_index: int,
    stage: str,
    observed_count: int,
    *,
    candidate_count: Optional[int] = None,
    mismatched_fields: Optional[Sequence[str]] = None,
) -> GmailError:
    detail = (
        "Gmail identity resolution failed for planned item {}: "
        "stage={}; observed_count={}; expected_count=1"
    ).format(item_index, stage, observed_count)
    if candidate_count is not None:
        detail += "; candidate_count={}".format(candidate_count)
    if mismatched_fields:
        detail += "; mismatched_fields={}".format(",".join(mismatched_fields))
    return GmailError(detail)


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
            permitted_bodies = tuple(
                body
                for label in MUTABLE_SOURCE_LABELS
                for body in (
                    {"addLabelIds": [label], "removeLabelIds": []},
                    {"addLabelIds": [], "removeLabelIds": [label]},
                )
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
            query=(
                ("q", query_value),
                ("maxResults", "10"),
                ("includeSpamTrash", "true"),
            ),
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

    def modify_label(
        self,
        gmail_message_id: str,
        label: str,
        *,
        add: bool = False,
        remove: bool = False,
    ) -> Dict[str, Any]:
        if label not in MUTABLE_SOURCE_LABELS:
            raise GmailError("Gmail label mutation is not allowlisted")
        if add == remove:
            raise GmailError("Exactly one of add or remove must be true")
        body = {
            "addLabelIds": [label] if add else [],
            "removeLabelIds": [label] if remove else [],
        }
        return self._request(
            "POST", "/messages/{}/modify".format(gmail_message_id), body=body
        )

    def modify_inbox_label(
        self, gmail_message_id: str, *, add: bool = False, remove: bool = False
    ) -> Dict[str, Any]:
        return self.modify_label(
            gmail_message_id,
            "INBOX",
            add=add,
            remove=remove,
        )


def header_map(message: Dict[str, Any]) -> Dict[str, str]:
    headers = message.get("payload", {}).get("headers", [])
    return {
        str(header.get("name", "")).lower(): str(header.get("value", ""))
        for header in headers
    }


def corroboration_mismatches(
    message: Dict[str, Any],
    item: Dict[str, Any],
    *,
    require_read: bool = False,
) -> List[str]:
    mismatches: List[str] = []
    headers = header_map(message)
    expected_id = str(item["message_id"]).strip("<>").lower()
    actual_id = headers.get("message-id", "").strip("<>").lower()
    if actual_id != expected_id:
        mismatches.append("message_id")
    if headers.get("subject", "") != item["subject"]:
        mismatches.append("subject")
    expected_sender = parseaddr(str(item.get("sender", "")))[1].lower()
    actual_sender = parseaddr(headers.get("from", ""))[1].lower()
    if expected_sender and actual_sender != expected_sender:
        mismatches.append("sender")
    internal_date = message.get("internalDate")
    if internal_date:
        actual_local_time = datetime.fromtimestamp(int(internal_date) / 1000)
        expected_local_time = datetime.strptime(
            str(item["received_at"])[:19],
            "%Y-%m-%dT%H:%M:%S",
        )
        if abs(actual_local_time - expected_local_time) > RECEIVED_AT_TOLERANCE:
            mismatches.append("received_date")
    if require_read:
        actual_read = "UNREAD" not in set(message.get("labelIds", []))
        if actual_read != bool(item["read"]):
            mismatches.append("read_state")
    return mismatches


def corroborates_plan_item(
    message: Dict[str, Any],
    item: Dict[str, Any],
    *,
    require_read: bool = False,
) -> bool:
    return not corroboration_mismatches(
        message,
        item,
        require_read=require_read,
    )


def resolve_unique_message(
    client: GmailClient,
    item: Dict[str, Any],
    *,
    item_index: int,
) -> Dict[str, Any]:
    references = client.list_by_rfc_message_id(str(item["message_id"]))
    if not references:
        raise _identity_resolution_error(
            item_index,
            "reference_lookup",
            0,
        )
    matches: List[Dict[str, Any]] = []
    single_candidate_mismatches: Optional[List[str]] = None
    for reference in references:
        message = client.get_metadata(reference["id"])
        mismatches = corroboration_mismatches(message, item)
        if len(references) == 1:
            single_candidate_mismatches = mismatches
        if not mismatches:
            matches.append(message)
    if len(matches) != 1:
        raise _identity_resolution_error(
            item_index,
            "metadata_corroboration",
            len(matches),
            candidate_count=len(references),
            mismatched_fields=single_candidate_mismatches,
        )
    return matches[0]


def resolve_messages_parallel(
    client: GmailClient,
    items: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not items or len(items) > PUBLIC_GMAIL_BATCH_LIMIT:
        raise GmailError(
            "Gmail batch size must be between 1 and {} messages".format(
                PUBLIC_GMAIL_BATCH_LIMIT
            )
        )
    with ThreadPoolExecutor(
        max_workers=min(GMAIL_NETWORK_WORKERS, len(items))
    ) as executor:
        return list(
            executor.map(
                lambda indexed_item: resolve_unique_message(
                    client,
                    indexed_item[1],
                    item_index=indexed_item[0],
                ),
                enumerate(items, start=1),
            )
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
    for item_index, (message, item) in enumerate(
        zip(metadata, items), start=1
    ):
        mismatches = corroboration_mismatches(
            message,
            item,
            require_read=True,
        )
        if mismatches:
            raise _identity_resolution_error(
                item_index,
                "read_state_corroboration",
                0,
                mismatched_fields=mismatches,
            )
    gmail_ids = [str(message["id"]) for message in metadata]
    with ThreadPoolExecutor(
        max_workers=min(GMAIL_NETWORK_WORKERS, len(gmail_ids))
    ) as executor:
        full_messages = list(executor.map(client.get_full, gmail_ids))
    for item_index, (full_message, item, gmail_id) in enumerate(
        zip(full_messages, items, gmail_ids), start=1
    ):
        if str(full_message.get("id", "")) != gmail_id:
            raise _identity_resolution_error(
                item_index,
                "full_response_binding",
                0,
            )
        mismatches = corroboration_mismatches(
            full_message,
            item,
            require_read=True,
        )
        if mismatches:
            raise _identity_resolution_error(
                item_index,
                "full_identity_corroboration",
                0,
                mismatched_fields=mismatches,
            )
    records: List[Dict[str, str]] = []
    for full_message, item in zip(full_messages, items):
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
                "ATTACHMENT_COUNT_SOURCE": "gmail_mime",
                "BODY_TRUNCATED": "true" if truncated else "false",
                "BODY": body,
            }
        )
    return records
