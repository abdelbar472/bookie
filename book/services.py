"""
Service layer for Book Service V3.
Orchestrates enrichment, MongoDB caching, and RAG notifications.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from pymongo.errors import PyMongoError

from .config import settings
from .database import check_db_health, get_collection, DatabaseUnavailableError
from .enrichment_engine import enrichment_engine
from .external_clients import _slugify, resolve_author, fetch_openlibrary_books_by_author
from .schemas import (
    AuthorProfile,
    AuthorSearchResponse,
    BookProfile,
    BookSearchResponse,
    HealthResponse,
    SeriesProfile,
    SeriesSearchResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _save_book(book: BookProfile) -> None:
    """Persist a BookProfile to MongoDB (upsert). Silent on DB unavailability."""
    try:
        col = get_collection("book_profiles")
        doc = book.model_dump(mode="json")
        await col.update_one({"work_id": book.work_id}, {"$set": doc}, upsert=True)
    except DatabaseUnavailableError:
        pass
    except PyMongoError as exc:
        logger.warning("Failed to save book '%s': %s", book.work_id, exc)


async def _save_author(author: AuthorProfile) -> None:
    """Persist an AuthorProfile to MongoDB (upsert). Silent on DB unavailability."""
    try:
        col = get_collection("author_profiles")
        doc = author.model_dump(mode="json")
        await col.update_one({"author_id": author.author_id}, {"$set": doc}, upsert=True)
    except DatabaseUnavailableError:
        pass
    except PyMongoError as exc:
        logger.warning("Failed to save author '%s': %s", author.author_id, exc)


async def _save_series(series: SeriesProfile) -> None:
    """Persist a SeriesProfile to MongoDB (upsert). Silent on DB unavailability."""
    try:
        col = get_collection("series_profiles")
        doc = series.model_dump(mode="json")
        await col.update_one({"series_id": series.series_id}, {"$set": doc}, upsert=True)
    except DatabaseUnavailableError:
        pass
    except PyMongoError as exc:
        logger.warning("Failed to save series '%s': %s", series.series_id, exc)


async def _notify_rag(book: BookProfile) -> None:
    """Optionally notify the RAG service about a new/updated book."""
    if not settings.ENABLE_RAG_NOTIFICATION:
        return
    try:
        from .grpc_client import notify_rag_indexing
        await notify_rag_indexing(book.model_dump(mode="json"))
    except Exception as exc:
        logger.debug("RAG notification skipped: %s", exc)


# ---------------------------------------------------------------------------
# BookService
# ---------------------------------------------------------------------------

class BookService:

    @staticmethod
    async def search_books(
        query: str,
        limit: int = 10,
        skip_cache: bool = False,
    ) -> BookSearchResponse:
        """
        Search for books.  Checks MongoDB cache first (unless skip_cache),
        then falls back to live enrichment via the EnrichmentEngine.
        """
        query = query.strip()

        # --- Cache lookup ---
        if not skip_cache:
            try:
                col = get_collection("book_profiles")
                cursor = col.find(
                    {"$text": {"$search": query}},
                    {"score": {"$meta": "textScore"}},
                ).sort([("score", {"$meta": "textScore"})]).limit(limit)
                cached = [BookProfile(**doc) async for doc in cursor]
                if cached:
                    logger.debug("Cache hit for book query '%s' (%d results)", query, len(cached))
                    sources = list({s for b in cached for s in b.description_sources} or ["cache"])
                    return BookSearchResponse(
                        query=query,
                        count=len(cached),
                        results=cached,
                        sources=sources or ["cache"],
                        from_cache=True,
                    )
            except DatabaseUnavailableError:
                pass
            except Exception as exc:
                logger.warning("Cache lookup failed: %s", exc)

        # --- Live enrichment ---
        include_arabic = settings.ENABLE_ARABIC_SEARCH
        books = await enrichment_engine.enrich_books_from_query(query, include_arabic=include_arabic)
        books = books[:limit]

        # Persist and notify in the background (best-effort)
        for book in books:
            await _save_book(book)
            await _notify_rag(book)

        sources = list({s for b in books for s in b.description_sources} or ["external"])
        return BookSearchResponse(
            query=query,
            count=len(books),
            results=books,
            sources=sources or ["external"],
            from_cache=False,
        )

    @staticmethod
    async def get_book_by_id(work_id: str) -> Optional[BookProfile]:
        """Fetch a single BookProfile by its work_id from MongoDB."""
        try:
            col = get_collection("book_profiles")
            doc = await col.find_one({"work_id": work_id})
            if doc:
                return BookProfile(**doc)
        except DatabaseUnavailableError:
            pass
        except Exception as exc:
            logger.warning("get_book_by_id failed for '%s': %s", work_id, exc)
        return None

    @staticmethod
    async def list_books(limit: int = 100, skip: int = 0) -> List[BookProfile]:
        """List cached books from MongoDB."""
        try:
            col = get_collection("book_profiles")
            cursor = col.find({}).skip(skip).limit(limit)
            return [BookProfile(**doc) async for doc in cursor]
        except DatabaseUnavailableError:
            return []
        except Exception as exc:
            logger.warning("list_books failed: %s", exc)
            return []


# ---------------------------------------------------------------------------
# AuthorService
# ---------------------------------------------------------------------------

class AuthorService:

    @staticmethod
    async def search_author(name: str) -> Optional[AuthorSearchResponse]:
        """
        Search for an author by name.
        Returns a rich AuthorSearchResponse including their bibliography.
        """
        name = name.strip()
        author_id = _slugify(name)

        # --- Cache lookup ---
        cached_author: Optional[AuthorProfile] = None
        try:
            col = get_collection("author_profiles")
            doc = await col.find_one({"author_id": author_id})
            if doc:
                cached_author = AuthorProfile(**doc)
        except DatabaseUnavailableError:
            pass
        except Exception as exc:
            logger.warning("Author cache lookup failed: %s", exc)

        # --- Fetch author's books ---
        book_response = await BookService.search_books(name, limit=settings.MAX_BOOKS_PER_QUERY)
        books = book_response.results

        # Normalize name for comparison: collapse dots+spaces so "J.K." matches "J. K."
        import re as _re
        def _norm(s: str) -> str:
            return _re.sub(r"[\s.]+", " ", s).strip().lower()

        name_norm = _norm(name)
        author_books = [
            b for b in books
            if any(name_norm in _norm(a) for a in b.authors)
        ]
        if not author_books:
            author_books = books  # fall back to all results if filtering is too strict

        if not author_books and not cached_author:
            return None

        # --- Build / update author profile ---
        if cached_author is None:
            author_profile = await enrichment_engine.enrich_author(name, author_books)
            await _save_author(author_profile)
        else:
            author_profile = cached_author

        return AuthorSearchResponse(
            query=name,
            author=author_profile,
            books=author_books,
            total_books=len(author_books),
        )

    @staticmethod
    async def get_author_by_id(author_id: str) -> Optional[AuthorProfile]:
        """Fetch a single AuthorProfile by ID from MongoDB."""
        try:
            col = get_collection("author_profiles")
            doc = await col.find_one({"author_id": author_id})
            if doc:
                return AuthorProfile(**doc)
        except DatabaseUnavailableError:
            pass
        except Exception as exc:
            logger.warning("get_author_by_id failed for '%s': %s", author_id, exc)
        return None


# ---------------------------------------------------------------------------
# SeriesService
# ---------------------------------------------------------------------------

class SeriesService:

    @staticmethod
    async def search_series(name: str) -> Optional[SeriesSearchResponse]:
        """
        Search for a book series by name.
        Returns series profile + constituent BookProfiles.
        """
        name = name.strip()
        series_id = _slugify(name)

        # --- Cache lookup ---
        try:
            col = get_collection("series_profiles")
            doc = await col.find_one({"series_id": series_id})
            if doc:
                series_profile = SeriesProfile(**doc)
                # Fetch associated books from cache
                book_col = get_collection("book_profiles")
                cursor = book_col.find({"series_name": {"$regex": name, "$options": "i"}}).limit(50)
                books = [BookProfile(**d) async for d in cursor]
                return SeriesSearchResponse(query=name, series=series_profile, books=books)
        except DatabaseUnavailableError:
            pass
        except Exception as exc:
            logger.warning("Series cache lookup failed: %s", exc)

        # --- Live enrichment ---
        book_response = await BookService.search_books(f"{name} series", limit=settings.MAX_BOOKS_PER_QUERY)
        all_books = book_response.results

        # Filter books that belong to this series
        name_lower = name.lower()
        series_books = [
            b for b in all_books
            if b.series_name and name_lower in b.series_name.lower()
        ]
        # Fallback 1: titles that start with or contain the series name
        # (catches "Harry Potter and the ..." style where series_name isn't extracted)
        if not series_books:
            series_books = [
                b for b in all_books
                if name_lower in b.title.lower()
            ]
        # Fallback 2: any book with any series_name from this result set
        if not series_books:
            series_books = [b for b in all_books if b.series_name]
        # Fallback 3: just use all results — they matched the series query string
        if not series_books:
            series_books = all_books
        if not series_books:
            return None

        series_profile = await enrichment_engine.enrich_series(name, series_books)
        await _save_series(series_profile)

        return SeriesSearchResponse(query=name, series=series_profile, books=series_books)

    @staticmethod
    async def get_series_by_id(series_id: str) -> Optional[SeriesProfile]:
        """Fetch a single SeriesProfile by ID from MongoDB."""
        try:
            col = get_collection("series_profiles")
            doc = await col.find_one({"series_id": series_id})
            if doc:
                return SeriesProfile(**doc)
        except DatabaseUnavailableError:
            pass
        except Exception as exc:
            logger.warning("get_series_by_id failed for '%s': %s", series_id, exc)
        return None


# ---------------------------------------------------------------------------
# HealthService
# ---------------------------------------------------------------------------

class HealthService:

    @staticmethod
    async def get_health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version="3.0.0",
            database=check_db_health(),
            timestamp=_utc_now(),
        )