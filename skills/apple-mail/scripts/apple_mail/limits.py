from typing import Iterator, Sequence, TypeVar


PUBLIC_GMAIL_BATCH_LIMIT = 50
MAIL_TRANSPORT_CHUNK_SIZE = 10
GMAIL_NETWORK_WORKERS = 10

T = TypeVar("T")


def chunks(
    items: Sequence[T],
    size: int = MAIL_TRANSPORT_CHUNK_SIZE,
) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
