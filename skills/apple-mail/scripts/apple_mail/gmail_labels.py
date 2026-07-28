from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, FrozenSet, List, Optional, Sequence

from .gmail import (
    FORBIDDEN_LABEL,
    PERMITTED_LABEL,
    GmailClient,
    GmailError,
    validate_archived_labels,
)
from .limits import GMAIL_NETWORK_WORKERS, PUBLIC_GMAIL_BATCH_LIMIT


class GmailMutationStateUnknown(GmailError):
    """Raised when authoritative reads cannot establish a mutation outcome."""


def _message_ids(gmail_messages: Sequence[Dict[str, Any]]) -> List[str]:
    gmail_ids = [str(message["id"]) for message in gmail_messages]
    if not gmail_ids:
        raise GmailError("Gmail mutation batch cannot be empty")
    if len(gmail_ids) > PUBLIC_GMAIL_BATCH_LIMIT:
        raise GmailError(
            "Gmail mutation batch cannot exceed {} messages".format(
                PUBLIC_GMAIL_BATCH_LIMIT
            )
        )
    if len(set(gmail_ids)) != len(gmail_ids):
        raise GmailError("Gmail resolution returned a duplicate message")
    return gmail_ids


def _metadata_labels(
    client: GmailClient, gmail_id: str
) -> FrozenSet[str]:
    message = client.get_metadata(gmail_id)
    if str(message.get("id", "")) != gmail_id:
        raise GmailError("Gmail reconciliation response ID changed")
    raw_labels = message.get("labelIds")
    if not isinstance(raw_labels, list):
        raise GmailError("Gmail reconciliation response omitted labels")
    return frozenset(str(label) for label in raw_labels)


def _read_labels(
    client: GmailClient, gmail_ids: Sequence[str]
) -> List[Optional[FrozenSet[str]]]:
    def read(gmail_id: str) -> Optional[FrozenSet[str]]:
        try:
            return _metadata_labels(client, gmail_id)
        except Exception:
            return None

    with ThreadPoolExecutor(
        max_workers=min(GMAIL_NETWORK_WORKERS, len(gmail_ids))
    ) as executor:
        return list(executor.map(read, gmail_ids))


def _restore_inbox(
    client: GmailClient,
    gmail_ids: Sequence[str],
    observations: Sequence[Optional[FrozenSet[str]]],
) -> None:
    restore_ids = [
        gmail_id
        for gmail_id, labels in zip(gmail_ids, observations)
        if labels is None or PERMITTED_LABEL not in labels
    ]
    if not restore_ids:
        return

    def restore(gmail_id: str) -> None:
        try:
            client.modify_inbox_label(gmail_id, add=True)
        except Exception:
            # A lost response is ambiguous in the same way as the failed
            # removal. The authoritative read below determines the outcome.
            pass

    with ThreadPoolExecutor(
        max_workers=min(GMAIL_NETWORK_WORKERS, len(restore_ids))
    ) as executor:
        list(executor.map(restore, restore_ids))


def _reconcile_failed_removal(
    client: GmailClient,
    gmail_ids: Sequence[str],
    original_error: Exception,
) -> None:
    observations = _read_labels(client, gmail_ids)
    _restore_inbox(client, gmail_ids, observations)
    final_labels = _read_labels(client, gmail_ids)

    unknown_count = sum(labels is None for labels in final_labels)
    if unknown_count:
        raise GmailMutationStateUnknown(
            "Gmail mutation state is unknown for {} of {} planned messages "
            "after authoritative reconciliation".format(
                unknown_count, len(gmail_ids)
            )
        ) from original_error

    incomplete_count = sum(
        PERMITTED_LABEL not in labels or FORBIDDEN_LABEL in labels
        for labels in final_labels
        if labels is not None
    )
    if incomplete_count:
        raise GmailError(
            "Gmail mutation failed and rollback is incomplete for {} of {} "
            "planned messages".format(incomplete_count, len(gmail_ids))
        ) from original_error

    raise original_error


def remove_inbox_labels_with_rollback(
    client: GmailClient,
    gmail_messages: Sequence[Dict[str, Any]],
) -> List[str]:
    """Remove INBOX atomically from the caller's perspective.

    When any concurrent request fails or returns an invalid result, every
    planned Gmail ID is read authoritatively. Any message observed without
    INBOX (and any message whose state could not initially be read) is restored,
    then every planned ID is read again before the original failure is exposed.
    """

    gmail_ids = _message_ids(gmail_messages)

    def remove(gmail_id: str) -> None:
        response = client.modify_inbox_label(gmail_id, remove=True)
        if str(response.get("id", "")) != gmail_id:
            raise GmailError("Gmail label-removal response ID changed")
        validate_archived_labels(response)

    errors: List[Exception] = []
    with ThreadPoolExecutor(
        max_workers=min(GMAIL_NETWORK_WORKERS, len(gmail_ids))
    ) as executor:
        futures = [executor.submit(remove, gmail_id) for gmail_id in gmail_ids]
        for future in futures:
            try:
                future.result()
            except Exception as error:
                errors.append(error)

    if errors:
        _reconcile_failed_removal(client, gmail_ids, errors[0])
    return gmail_ids
