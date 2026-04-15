"""
V3 Business Logic Layer
Book-only operations: search, fetch, cache, and health.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import DatabaseUnavailableError, check_db_health, get_collection
from .enrichment_engine import enrichment_engine
from .external_clients import _is_arabic
from .schemas import BookProfile, BookSearchResponse

logger = logging.getLogger(__name__)


class BookService:
    """Main service for book operations."""

    @staticmethod
    async def search_books(query: str, limit: int = 10, skip_cache: bool = False) -> BookSearchResponse:
        """Search books, optionally using cache first."""
        logger.info("Searching books: query='%s', limit=%s", query, limit)

        if not skip_cache:
            cached = await BookService._get_cached_books(query)
            if cached:
                logger.info("Returning %s cached results", len(cached))
                return BookSearchResponse(
                    query=query,
                    count=len(cached),
                    results=cached[:limit],
                    sources=["cache"],
                    from_cache=True,
                )

        include_arabic = _is_arabic(query)
        profiles = await enrichment_engine.enrich_books_from_query(query, include_arabic)

        if not profiles:
            return BookSearchResponse(
                query=query,
                count=0,
                results=[],
                sources=[],
                from_cache=False,
            )

        await BookService._cache_books(profiles, query)

        return BookSearchResponse(
            query=query,
            count=len(profiles),
            results=profiles[:limit],
            sources=["google_books", "openlibrary"],
            from_cache=False,
        )

    @staticmethod
    async def get_book_by_id(work_id: str) -> Optional[BookProfile]:
        """Get a specific book by work ID."""
        try:
            col = get_collection("book_profiles")
            doc = await col.find_one({"work_id": work_id})
            if doc:
                return BookProfile(**doc)
        except DatabaseUnavailableError:
            pass
        return None

    @staticmethod
    async def list_books(limit: int = 100, skip: int = 0) -> List[BookProfile]:
        """List cached books."""
        try:
            col = get_collection("book_profiles")
            cursor = col.find().skip(skip).limit(limit)
            docs = await cursor.to_list(length=limit)
            return [BookProfile(**doc) for doc in docs]
        except DatabaseUnavailableError:
            return []

    @staticmethod
    async def _get_cached_books(query: str) -> List[BookProfile]:
        """Try to get books from text cache."""
        try:
            col = get_collection("book_profiles")
            cursor = col.find({"$text": {"$search": query}}).limit(20)
            docs = await cursor.to_list(length=20)
            return [BookProfile(**doc) for doc in docs]
        except Exception as exc:
            logger.debug("Cache lookup failed: %s", exc)
            return []

    @staticmethod
    async def _cache_books(profiles: List[BookProfile], query: str) -> None:
        """Store enriched books in cache."""
        try:
            col = get_collection("book_profiles")
            for profile in profiles:
                await col.update_one(
                    {"work_id": profile.work_id},
                    {
                        "$set": {
                            **profile.model_dump(),
                            "cached_at": datetime.now(timezone.utc),
                            "cache_query": query,
                        }
                    },
                    upsert=True,
                )
            logger.info("Cached %s books", len(profiles))
        except Exception as exc:
            logger.warning("Failed to cache books: %s", exc)


class HealthService:
    """Health check service."""

    @staticmethod
    async def get_health() -> Dict[str, Any]:
        """Get service health status."""
        db_health = check_db_health()

        return {
            "status": "healthy" if db_health["connected"] else "degraded",
            "version": "3.0.0",
            "database": db_health,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }