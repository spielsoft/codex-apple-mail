from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from .gmail import (
    FORBIDDEN_LABEL,
    MUTABLE_SOURCE_LABELS,
    GmailClient,
    GmailError,
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


def _response_labels(
    response: Dict[str, Any],
    gmail_id: str,
) -> Optional[FrozenSet[str]]:
    if str(response.get("id", "")) != gmail_id:
        raise GmailError("Gmail label-removal response ID changed")
    raw_labels = response.get("labelIds")
    if not isinstance(raw_labels, list):
        return None
    return frozenset(str(label) for label in raw_labels)


def _remove_label_snapshots(
    client: GmailClient,
    gmail_ids: Sequence[str],
    label: str,
) -> Tuple[List[Optional[FrozenSet[str]]], List[Exception]]:
    def remove(gmail_id: str) -> Optional[FrozenSet[str]]:
        return _response_labels(
            _modify_label(
                client,
                gmail_id,
                label,
                remove=True,
            ),
            gmail_id,
        )

    snapshots: List[Optional[FrozenSet[str]]] = [
        None for _ in gmail_ids
    ]
    errors: List[Exception] = []
    with ThreadPoolExecutor(
        max_workers=min(GMAIL_NETWORK_WORKERS, len(gmail_ids))
    ) as executor:
        futures = [executor.submit(remove, gmail_id) for gmail_id in gmail_ids]
        for index, future in enumerate(futures):
            try:
                snapshots[index] = future.result()
            except Exception as error:
                errors.append(error)
    return snapshots, errors


def _fill_missing_snapshots(
    client: GmailClient,
    gmail_ids: Sequence[str],
    snapshots: Sequence[Optional[FrozenSet[str]]],
) -> List[Optional[FrozenSet[str]]]:
    complete = list(snapshots)
    missing_indices = [
        index
        for index, labels in enumerate(complete)
        if labels is None
    ]
    if not missing_indices:
        return complete
    missing_labels = _read_labels(
        client,
        [gmail_ids[index] for index in missing_indices],
    )
    for index, labels in zip(missing_indices, missing_labels):
        complete[index] = labels
    return complete


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

    observed_labels, errors = _remove_label_snapshots(
        client,
        gmail_ids,
        source_label,
    )
    if errors:
        _reconcile_failed_removal(
            client,
            gmail_ids,
            source_label,
            errors[0],
        )

    observed_labels = _fill_missing_snapshots(
        client,
        gmail_ids,
        observed_labels,
    )
    if any(labels is None for labels in observed_labels):
        _reconcile_failed_removal(
            client,
            gmail_ids,
            source_label,
            GmailError(
                "Gmail source-label removal could not be confirmed"
            ),
        )

    if source_label == "SPAM":
        inbox_ids = [
            gmail_id
            for gmail_id, labels in zip(gmail_ids, observed_labels)
            if labels is not None and "INBOX" in labels
        ]
        if inbox_ids:
            cleanup_labels, cleanup_errors = _remove_label_snapshots(
                client,
                inbox_ids,
                "INBOX",
            )
            if cleanup_errors:
                _reconcile_failed_removal(
                    client,
                    gmail_ids,
                    source_label,
                    cleanup_errors[0],
                )
            cleanup_labels = _fill_missing_snapshots(
                client,
                inbox_ids,
                cleanup_labels,
            )
            cleanup_by_id = dict(zip(inbox_ids, cleanup_labels))
            for index, gmail_id in enumerate(gmail_ids):
                if gmail_id in cleanup_by_id:
                    observed_labels[index] = cleanup_by_id[gmail_id]

    final_labels = observed_labels
    invalid_count = sum(
        labels is None
        or source_label in labels
        or FORBIDDEN_LABEL in labels
        or (source_label == "SPAM" and "INBOX" in labels)
        for labels in final_labels
    )
    if invalid_count:
        _reconcile_failed_removal(
            client,
            gmail_ids,
            source_label,
            GmailError(
                "Gmail source-label removal did not reach the required "
                "final state"
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
