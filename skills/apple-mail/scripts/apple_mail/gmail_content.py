import base64
from html.parser import HTMLParser
from typing import Any, Dict, List


class GmailBodyUnavailable(RuntimeError):
    """The selected body cannot be read without a prohibited attachment fetch."""


def _decode_body_data(data: str) -> str:
    padded = data + ("=" * (-len(data) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise GmailBodyUnavailable(
            "Gmail message body is not valid inline base64url"
        ) from error
    return raw.decode("utf-8", errors="replace")


def _walk_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    output = [payload]
    for part in payload.get("parts", []) or []:
        if isinstance(part, dict):
            output.extend(_walk_payload(part))
    return output


def _body_state(part: Dict[str, Any]) -> str:
    body = part.get("body", {})
    if not isinstance(body, dict):
        return "unavailable"
    try:
        size = int(body.get("size", 0) or 0)
    except (TypeError, ValueError):
        return "unavailable"
    if "data" in body:
        if body.get("data"):
            return "inline"
        return "unavailable" if size > 0 else "empty"
    if body.get("attachmentId") or size > 0:
        return "unavailable"
    return "empty"


def _text_body_parts(
    payload: Dict[str, Any], mime_type: str
) -> List[Dict[str, Any]]:
    return [
        part
        for part in _walk_payload(payload)
        if part.get("mimeType") == mime_type
        and not str(part.get("filename", ""))
    ]


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
        raise GmailBodyUnavailable("Gmail message payload is unavailable")

    for mime_type in ("text/plain", "text/html"):
        parts = _text_body_parts(payload, mime_type)
        if not parts:
            continue
        if any(_body_state(part) == "unavailable" for part in parts):
            raise GmailBodyUnavailable(
                "Gmail selected text body is not available inline"
            )
        values = [
            _decode_body_data(str(part.get("body", {}).get("data", "")))
            for part in parts
            if _body_state(part) == "inline"
        ]
        if mime_type == "text/plain":
            if values:
                return "\n".join(values)
            continue
        parser = _PlainTextHTMLParser()
        for value in values:
            parser.feed(value)
            parser.fragments.append("\n")
        return parser.text()
    return ""


def _part_attachment_count(part: Dict[str, Any]) -> int:
    filename = str(part.get("filename", ""))
    headers = part.get("headers", []) or []
    disposition = ""
    for header in headers:
        if str(header.get("name", "")).casefold() == "content-disposition":
            disposition = str(header.get("value", "")).casefold()
            break
    if filename or disposition.startswith("attachment"):
        return 1
    children = part.get("parts", []) or []
    if children:
        return sum(
            _part_attachment_count(child)
            for child in children
            if isinstance(child, dict)
        )
    mime_type = str(part.get("mimeType", "")).casefold()
    body = part.get("body", {})
    if (
        isinstance(body, dict)
        and body.get("attachmentId")
        and mime_type not in ("text/plain", "text/html")
    ):
        return 1
    return 0


def attachment_count(message: Dict[str, Any]) -> int:
    """Return a Gmail MIME-part count, not an Apple Mail object count."""
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        return 0
    return _part_attachment_count(payload)
