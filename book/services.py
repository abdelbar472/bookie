"""
V3 Business Logic Layer
Coordinates enrichment, storage, and external service integration
"""
import asyncio
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
            cursor = col.find({
                "$or": [
                    {"title": {"$regex": query, "$options": "i"}},
                    {"keywords": {"$regex": query, "$options": "i"}},
                ]
            }).limit(20)
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

        # 1. Check cache first — verify it has books
        cached = await AuthorService._get_cached_author(name)
        if cached:
            books = await BookService.list_books(limit=200)
            author_books = [
                b
                for b in books
                if b.primary_author.lower() == name.lower()
                or any(name.lower() in a.lower() for a in b.authors)
            ]
            if author_books:
                logger.info("Cache hit for author '%s' with %s books", name, len(author_books))
                return AuthorSearchResponse(
                    query=name,
                    author=cached,
                    books=author_books,
                    total_books=len(author_books),
                )
            else:
                logger.warning("Cache hit for author '%s' but NO books — stale cache, refetching", name)

        # 2. Fetch author-specific books from Google Books
        logger.info('Fetching from Google Books API: inauthor:"%s"', name)
        raw_items = await fetch_google_books(f'inauthor:"{name}"', max_results=40)
        logger.info("Google Books returned %s items for author '%s'", len(raw_items), name)

        # 3. Fallback to OpenLibrary if Google returns nothing
        if not raw_items:
            logger.info("Trying OpenLibrary for author: %s", name)
            raw_items = await fetch_openlibrary_books_by_author(name, limit=30)
            logger.info("OpenLibrary returned %s items for author '%s'", len(raw_items), name)

        if not raw_items:
            logger.error("NO raw items found for author '%s' from ANY source", name)
            return None

        # 4. Enrich the raw items directly
        grouped = enrichment_engine._group_editions(raw_items)
        logger.info("Grouped into %s unique works for author '%s'", len(grouped), name)

        book_profiles = []
        for work_data in grouped:
            try:
                profile = await enrichment_engine._create_book_profile(work_data)
                book_profiles.append(profile)
            except Exception as e:
                logger.error("Failed to enrich work for author '%s': %s", name, e)
                continue

        logger.info("Created %s book profiles for author '%s'", len(book_profiles), name)

        if not book_profiles:
            logger.error("ZERO book profiles created for author '%s'", name)
            return None

        # 5. Filter to ensure we only get this author's books
        author_books = [
            b
            for b in book_profiles
            if name.lower() in b.primary_author.lower()
            or any(name.lower() in a.lower() for a in b.authors)
        ]

        logger.info("Author filter matched %s/%s books for '%s'", len(author_books), len(book_profiles), name)

        # 6. CRITICAL FIX: If filter is too strict, use ALL fetched books
        # This happens when author name variations don't match exactly
        if not author_books:
            logger.warning("Strict filter returned 0 for '%s', using all %s fetched books", name, len(book_profiles))
            author_books = book_profiles

        if not author_books:
            logger.error("ZERO books for author '%s' after all attempts", name)
            return None

        # 7. Build author profile from these books
        author_profile = await enrichment_engine.enrich_author(name, author_books)

        # 8. Only cache if we have actual books
        if len(author_books) > 0:
            await AuthorService._cache_author(author_profile)
            await BookService._cache_books(author_books, f"author:{name}")
            logger.info("SUCCESS — Cached author '%s' with %s books", name, len(author_books))
        else:
            logger.warning("NOT caching author '%s' — zero books", name)

        return AuthorSearchResponse(
            query=name,
            author=author_profile,
            books=author_books,
            total_books=len(author_books),
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
        """Search for book series with timeout protection."""
        logger.info("Searching series: %s", name)

        # 1. Check cache first — verify it has books
        cached = await SeriesService._get_cached_series(name)
        if cached:
            try:
                all_books = await BookService.list_books(limit=200)
                series_books = [b for b in all_books if b.series_name and name.lower() in b.series_name.lower()]
                if series_books:
                    logger.info("Cache hit for series '%s' with %s books", name, len(series_books))
                    return SeriesSearchResponse(query=name, series=cached, books=series_books)
                else:
                    logger.warning("Cache hit for series '%s' but NO books — stale cache, refetching", name)
            except Exception:
                pass

        # 2. Fetch books for this series
        try:
            books = await asyncio.wait_for(
                enrichment_engine.enrich_books_from_query(f"{name} series", include_arabic=_is_arabic(name)),
                timeout=12.0
            )
            logger.info("Series query '%s series' returned %s books", name, len(books))
        except asyncio.TimeoutError:
            logger.warning("Series enrichment timed out for: %s", name)
            books = []

        # 3. Also try a broader search
        if not books:
            try:
                books = await asyncio.wait_for(
                    enrichment_engine.enrich_books_from_query(name, include_arabic=_is_arabic(name)),
                    timeout=10.0
                )
                logger.info("Broad query '%s' returned %s books", name, len(books))
            except asyncio.TimeoutError:
                logger.warning("Broad series search timed out for: %s", name)
                books = []

        # 4. Filter to actual series matches
        series_books = [
            b for b in books
            if b.series_name and name.lower() in b.series_name.lower()
        ]
        logger.info("Series name filter: %s books match", len(series_books))

        # 5. Also include books where the title contains the series name
        if not series_books:
            series_books = [
                b for b in books
                if name.lower() in b.title.lower()
            ]
            logger.info("Title filter: %s books match", len(series_books))

        # 6. Final fallback
        if not series_books:
            series_books = books
            logger.info("Using all %s fetched books as fallback", len(books))

        if not series_books:
            logger.warning("No books found for series: %s", name)
            return None

        # 7. Determine actual series name from books
        series_names = [b.series_name for b in series_books if b.series_name]
        if series_names:
            actual_name = Counter(series_names).most_common(1)[0][0]
            actual_books = [b for b in series_books if b.series_name == actual_name]
            logger.info("Detected series name '%s' with %s books", actual_name, len(actual_books))
        else:
            actual_name = name
            actual_books = series_books
            logger.info("No series name detected, using '%s' with %s books", actual_name, len(actual_books))

        # 8. Build series profile
        series_profile = await enrichment_engine.enrich_series(actual_name, actual_books)

        # 9. Only cache if we have actual books
        if len(actual_books) > 0:
            await SeriesService._cache_series(series_profile)
            await BookService._cache_books(actual_books, f"series:{name}")
            logger.info("SUCCESS — Cached series '%s' with %s books", actual_name, len(actual_books))
        else:
            logger.warning("NOT caching series '%s' — zero books", name)

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