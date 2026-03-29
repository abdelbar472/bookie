import logging
from typing import Iterable

logger = logging.getLogger(__name__)


async def notify_new_books(book_ids: Iterable[str]) -> None:
    """Placeholder hook for social fan-out; kept non-blocking for ingestion flow."""
    ids = [book_id for book_id in book_ids if book_id]
    if not ids:
        return
    logger.debug("Social notification skipped for %d books", len(ids))

