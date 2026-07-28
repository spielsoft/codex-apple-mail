from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, FrozenSet, List, Optional, Sequence

from .gmail import (
    FORBIDDEN_LABEL,
    MUTABLE_SOURCE_LABELS,
    GmailClient,
    GmailError,
    validate_removed_source_label,
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


def _modify_label(
    client: GmailClient,
    gmail_id: str,
    label: str,
    *,
    add: bool = False,
    remove: bool = False,
) -> Dict[str, Any]:
    if label == "INBOX" and not hasattr(client, "modify_label"):
        return client.modify_inbox_label(
            gmail_id,
            add=add,
            remove=remove,
        )
    return client.modify_label(
        gmail_id,
        label,
        add=add,
        remove=remove,
    )


def _restore_source_state(
    client: GmailClient,
    gmail_ids: Sequence[str],
    observations: Sequence[Optional[FrozenSet[str]]],
    source_label: str,
) -> None:
    restore_ids = [
        (gmail_id, labels)
        for gmail_id, labels in zip(gmail_ids, observations)
        if (
            labels is None
            or source_label not in labels
            or (source_label == "SPAM" and "INBOX" in labels)
        )
    ]
    if not restore_ids:
        return

    def restore(item: Any) -> None:
        gmail_id, labels = item
        if labels is None or source_label not in labels:
            try:
                _modify_label(
                    client,
                    gmail_id,
                    source_label,
                    add=True,
                )
            except Exception:
                # The authoritative read below determines whether a lost
                # response still changed the label.
                pass
        if source_label == "SPAM" and (
            labels is None or "INBOX" in labels
        ):
            try:
                _modify_label(
                    client,
                    gmail_id,
                    "INBOX",
                    remove=True,
                )
            except Exception:
                # Continue to the authoritative final read even if cleanup
                # returned an ambiguous response.
                pass

    with ThreadPoolExecutor(
        max_workers=min(GMAIL_NETWORK_WORKERS, len(restore_ids))
    ) as executor:
        list(executor.map(restore, restore_ids))


def _reconcile_failed_removal(
    client: GmailClient,
    gmail_ids: Sequence[str],
    source_label: str,
    original_error: Exception,
) -> None:
    observations = _read_labels(client, gmail_ids)
    _restore_source_state(
        client,
        gmail_ids,
        observations,
        source_label,
    )
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
        (
            source_label not in labels
            or FORBIDDEN_LABEL in labels
            or (source_label == "SPAM" and "INBOX" in labels)
        )
        for labels in final_labels
        if labels is not None
    )
    if incomplete_count:
        raise GmailError(
            "Gmail mutation failed and rollback is incomplete for {} of {} "
            "planned messages".format(incomplete_count, len(gmail_ids))
        ) from original_error

    raise original_error


def remove_source_labels_with_rollback(
    client: GmailClient,
    gmail_messages: Sequence[Dict[str, Any]],
    source_label: str,
) -> List[str]:
    """Remove one allowlisted source label atomically from the caller's view.

    When any concurrent request fails or returns an invalid result, every
    planned Gmail ID is read authoritatively. Any message observed without
    the source label (and any message whose state could not initially be read)
    is restored, then every planned ID is read again before the original
    failure is exposed.
    """

    if source_label not in MUTABLE_SOURCE_LABELS:
        raise GmailError("Gmail source label is not allowlisted")
    gmail_ids = _message_ids(gmail_messages)

    def remove(gmail_id: str) -> None:
        response = _modify_label(
            client,
            gmail_id,
            source_label,
            remove=True,
        )
        if str(response.get("id", "")) != gmail_id:
            raise GmailError("Gmail label-removal response ID changed")
        raw_labels = response.get("labelIds")
        if not isinstance(raw_labels, list):
            raise GmailError("Gmail label-removal response omitted labels")
        if source_label == "SPAM" and "INBOX" in set(raw_labels):
            response = _modify_label(
                client,
                gmail_id,
                "INBOX",
                remove=True,
            )
            if str(response.get("id", "")) != gmail_id:
                raise GmailError("Gmail label-removal response ID changed")
        validate_removed_source_label(response, source_label)

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
        _reconcile_failed_removal(
            client,
            gmail_ids,
            source_label,
            errors[0],
        )
    if source_label == "SPAM":
        final_labels = _read_labels(client, gmail_ids)
        invalid_count = sum(
            labels is None
            or source_label in labels
            or "INBOX" in labels
            or FORBIDDEN_LABEL in labels
            for labels in final_labels
        )
        if invalid_count:
            _reconcile_failed_removal(
                client,
                gmail_ids,
                source_label,
                GmailError(
                    "Gmail SPAM removal did not reach the required final state"
                ),
            )
    return gmail_ids


def remove_inbox_labels_with_rollback(
    client: GmailClient,
    gmail_messages: Sequence[Dict[str, Any]],
) -> List[str]:
    return remove_source_labels_with_rollback(
        client,
        gmail_messages,
        "INBOX",
    )


def remove_spam_labels_with_rollback(
    client: GmailClient,
    gmail_messages: Sequence[Dict[str, Any]],
) -> List[str]:
    return remove_source_labels_with_rollback(
        client,
        gmail_messages,
        "SPAM",
    )
