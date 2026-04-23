"""
V3 Business Logic Layer
Coordinates enrichment, storage, and external service integration
"""

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import DatabaseUnavailableError, check_db_health, get_collection
from .enrichment_engine import enrichment_engine
from .external_clients import fetch_google_books, fetch_openlibrary_books_by_author, _is_arabic, _slugify
from .schemas import (
    AuthorProfile,
    AuthorSearchResponse,
    BookProfile,
    BookSearchResponse,
    SeriesProfile,
    SeriesSearchResponse,
)

logger = logging.getLogger(__name__)


class BookService:
    """Main service for book operations."""

    @staticmethod
    async def search_books(query: str, limit: int = 10, skip_cache: bool = False) -> BookSearchResponse:
        """Search for books with enrichment and caching."""
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
        """Get specific book by work ID."""
        try:
            col = get_collection("book_profiles")
            doc = await col.find_one({"work_id": work_id})
            if doc:
                return BookProfile(**doc)
        except DatabaseUnavailableError:
            pass
        return None

    @staticmethod
    async def _get_cached_books(query: str) -> List[BookProfile]:
        """Try to get books from cache."""
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
        """Store enriched books in cache and optionally notify RAG service."""
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

            # Best-effort async notification to RAG service.
            from .config import settings as service_settings

            if service_settings.ENABLE_RAG_NOTIFICATION:
                from .grpc_client import notify_rag_indexing

                for profile in profiles:
                    try:
                        await notify_rag_indexing(profile.model_dump())
                    except Exception as notify_exc:
                        logger.warning("RAG notification failed for %s: %s", profile.work_id, notify_exc)

        except Exception as exc:
            logger.warning("Failed to cache books: %s", exc)

    @staticmethod
    async def list_books(limit: int = 100, skip: int = 0) -> List[BookProfile]:
        """List all cached books."""
        try:
            col = get_collection("book_profiles")
            cursor = col.find().skip(skip).limit(limit)
            docs = await cursor.to_list(length=limit)
            return [BookProfile(**doc) for doc in docs]
        except DatabaseUnavailableError:
            return []


class AuthorService:
    """Service for author operations."""

    @staticmethod
    async def search_author(name: str) -> Optional[AuthorSearchResponse]:
        """Search for author and related books."""
        logger.info("Searching author: %s", name)

        cached = await AuthorService._get_cached_author(name)
        if cached:
            books = await BookService.list_books(limit=50)
            author_books = [
                b
                for b in books
                if b.primary_author.lower() == name.lower()
                or any(name.lower() in a.lower() for a in b.authors)
            ]
            return AuthorSearchResponse(
                query=name,
                author=cached,
                books=author_books,
                total_books=len(author_books),
            )

        raw_items = await fetch_google_books(f'inauthor:"{name}"', max_results=40)
        if not raw_items:
            raw_items = await fetch_openlibrary_books_by_author(name, limit=30)

        if not raw_items:
            return None

        # Reuse enrichment query flow, then narrow to requested author.
        book_profiles = await enrichment_engine.enrich_books_from_query(name, False)
        book_profiles = [
            b
            for b in book_profiles
            if name.lower() in b.primary_author.lower()
            or any(name.lower() in a.lower() for a in b.authors)
        ]

        author_profile = await enrichment_engine.enrich_author(name, book_profiles)
        await AuthorService._cache_author(author_profile)

        return AuthorSearchResponse(
            query=name,
            author=author_profile,
            books=book_profiles,
            total_books=len(book_profiles),
        )

    @staticmethod
    async def get_author_by_id(author_id: str) -> Optional[AuthorProfile]:
        """Get author by ID."""
        try:
            col = get_collection("author_profiles")
            doc = await col.find_one({"author_id": author_id})
            if doc:
                return AuthorProfile(**doc)
        except DatabaseUnavailableError:
            pass
        return None

    @staticmethod
    async def _get_cached_author(name: str) -> Optional[AuthorProfile]:
        """Try to get author from cache."""
        try:
            col = get_collection("author_profiles")
            doc = await col.find_one(
                {
                    "$or": [
                        {"author_id": _slugify(name)},
                        {"name": {"$regex": name, "$options": "i"}},
                    ]
                }
            )
            if doc:
                return AuthorProfile(**doc)
        except Exception as exc:
            logger.debug("Author cache lookup failed: %s", exc)
        return None

    @staticmethod
    async def _cache_author(profile: AuthorProfile) -> None:
        """Store author in cache."""
        try:
            col = get_collection("author_profiles")
            await col.update_one(
                {"author_id": profile.author_id},
                {
                    "$set": {
                        **profile.model_dump(),
                        "cached_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            logger.info("Cached author: %s", profile.name)
        except Exception as exc:
            logger.warning("Failed to cache author: %s", exc)


class SeriesService:
    """Service for series operations."""

    @staticmethod
    async def search_series(name: str) -> Optional[SeriesSearchResponse]:
        """Search for book series and build reading order profile."""
        logger.info("Searching series: %s", name)

        cached = await SeriesService._get_cached_series(name)
        if cached:
            books: List[BookProfile] = []
            for book_id in cached.reading_order[:20]:
                book = await BookService.get_book_by_id(book_id)
                if book:
                    books.append(book)

            return SeriesSearchResponse(
                query=name,
                series=cached,
                books=books,
            )

        query = f"{name} series"
        book_profiles = await enrichment_engine.enrich_books_from_query(query, False)

        series_books = [
            b for b in book_profiles if b.series_name and name.lower() in b.series_name.lower()
        ]

        if not series_books:
            book_profiles = await enrichment_engine.enrich_books_from_query(name, False)
            series_books = [b for b in book_profiles if b.series_name]

        if not series_books:
            series_books = book_profiles

        if not series_books:
            return None

        series_names = [b.series_name for b in series_books if b.series_name]
        if series_names:
            actual_name = Counter(series_names).most_common(1)[0][0]
            actual_books = [b for b in series_books if b.series_name == actual_name]
        else:
            actual_name = name
            actual_books = series_books

        series_profile = await enrichment_engine.enrich_series(actual_name, actual_books)
        await SeriesService._cache_series(series_profile)

        return SeriesSearchResponse(
            query=name,
            series=series_profile,
            books=actual_books,
        )

    @staticmethod
    async def get_series_by_id(series_id: str) -> Optional[SeriesProfile]:
        """Get series by ID."""
        try:
            col = get_collection("series_profiles")
            doc = await col.find_one({"series_id": series_id})
            if doc:
                return SeriesProfile(**doc)
        except DatabaseUnavailableError:
            pass
        return None

    @staticmethod
    async def _get_cached_series(name: str) -> Optional[SeriesProfile]:
        """Try to get series from cache."""
        try:
            col = get_collection("series_profiles")
            doc = await col.find_one(
                {
                    "$or": [
                        {"series_id": _slugify(name)},
                        {"series_name": {"$regex": name, "$options": "i"}},
                    ]
                }
            )
            if doc:
                return SeriesProfile(**doc)
        except Exception as exc:
            logger.debug("Series cache lookup failed: %s", exc)
        return None

    @staticmethod
    async def _cache_series(profile: SeriesProfile) -> None:
        """Store series in cache."""
        try:
            col = get_collection("series_profiles")
            await col.update_one(
                {"series_id": profile.series_id},
                {
                    "$set": {
                        **profile.model_dump(),
                        "cached_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            logger.info("Cached series: %s", profile.series_name)
        except Exception as exc:
            logger.warning("Failed to cache series: %s", exc)


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

