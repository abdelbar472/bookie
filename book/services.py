"""
V3 Business Logic Layer
Coordinates enrichment, storage, and external service integration
"""
import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import settings
from .database import DatabaseUnavailableError, check_db_health, get_collection
from .enrichment_engine import enrichment_engine
from .external_clients import (
    build_author_name_variants,
    fetch_author_aliases,
    fetch_google_books,
    fetch_openlibrary_author_works,
    fetch_openlibrary_books_by_author,
    _is_arabic,
    _slugify, fetch_arabic_books,
)
from .schemas import (
    AuthorProfile,
    AuthorSearchResponse,
    BookProfile,
    BookSearchResponse,
    SeriesProfile,
    SeriesSearchResponse,
)

logger = logging.getLogger(__name__)


def _normalize_lookup(text: str) -> str:
    return " ".join((text or "").lower().replace(".", " ").replace("-", " ").split())


def _name_variants(name: str) -> List[str]:
    variants = {_normalize_lookup(name)}
    for variant in build_author_name_variants(name):
        variants.add(_normalize_lookup(variant))
    return [v for v in variants if v]


def _merge_unique_items(*sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for src in sources:
        for item in src:
            volume = item.get("volumeInfo", {})
            key_parts = [
                str(item.get("id") or "").strip(),
                str(volume.get("title") or "").strip().lower(),
                "|".join((a or "").strip().lower() for a in (volume.get("authors") or [])[:2]),
            ]
            key = "::".join(part for part in key_parts if part)
            if not key:
                continue
            if key not in merged:
                merged[key] = item
    return list(merged.values())


def _author_matches(book: BookProfile, query_name: str) -> bool:
    variants = _name_variants(query_name)
    candidates = [_normalize_lookup(book.primary_author)] + [_normalize_lookup(a) for a in book.authors]
    for candidate in candidates:
        if not candidate:
            continue
        if any(v in candidate or candidate in v for v in variants):
            return True
    return False


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

            if service_settings.ENABLE_RAG_NOTIFICATION and profiles:
                # Keep API latency low: do indexing notifications in background.
                asyncio.create_task(BookService._notify_rag_indexing(profiles))

        except Exception as exc:
            logger.warning("Failed to cache books: %s", exc)

    @staticmethod
    async def _notify_rag_indexing(profiles: List[BookProfile]) -> None:
        from .grpc_client import notify_rag_indexing

        failed = 0
        for profile in profiles:
            try:
                await notify_rag_indexing(profile.model_dump())
            except Exception:
                failed += 1
        if failed:
            logger.warning("RAG notification background task failed for %s/%s books", failed, len(profiles))

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

        # 1. Check cache first
        cached = await AuthorService._get_cached_author(name)
        if cached:
            books = await BookService.list_books(limit=200)
            author_books = [b for b in books if _author_matches(b, name)]
            if author_books:
                logger.info("Cache hit for author '%s' with %s books", name, len(author_books))
                return AuthorSearchResponse(
                    query=name, author=cached, books=author_books, total_books=len(author_books)
                )
            else:
                logger.warning("Cache hit for author '%s' but NO books — stale cache, refetching", name)

        # 2. RESOLVE NAMES — this is the key fix
        from .external_clients import resolve_author_names
        name_data = await resolve_author_names(name)

        arabic_names = name_data.get("arabic_names", [])
        latin_names = name_data.get("latin_names", [])
        all_variants = name_data.get("variants", [name])

        logger.info("Resolved '%s' → %s variants (%s Arabic, %s Latin)",
                   name, len(all_variants), len(arabic_names), len(latin_names))

        # 3. Build search candidates: Arabic names first (for Arabic APIs), then Latin
        search_candidates = []

        # Arabic candidates → use with Arabic Google Books
        for an in arabic_names[:2]:
            if an not in [c[1] for c in search_candidates]:
                search_candidates.append(("ar", an))

        # Latin candidates → use with English Google Books + OpenLibrary
        for ln in latin_names[:4]:
            if ln not in [c[1] for c in search_candidates]:
                search_candidates.append(("en", ln))

        # Fallback to input
        if not search_candidates:
            search_candidates.append(("en" if not _is_arabic(name) else "ar", name))

        raw_items: List[Dict[str, Any]] = []
        min_results = max(1, settings.AUTHOR_SEARCH_MIN_RESULTS)

        for lang, candidate in search_candidates[:6]:
            logger.info('Fetching for author candidate: "%s" (lang=%s)', candidate, lang)

            # Google Books — language-appropriate
            try:
                if lang == "ar":
                    google_results = await asyncio.wait_for(
                        fetch_arabic_books(candidate, max_results=24),
                        timeout=9.0,
                    )
                else:
                    google_results = await asyncio.wait_for(
                        fetch_google_books(f'inauthor:"{candidate}"', max_results=24),
                        timeout=9.0,
                    )
            except asyncio.TimeoutError:
                logger.warning("Google query timed out for '%s'", candidate)
                google_results = []
            except Exception as exc:
                logger.warning("Google query failed for '%s': %s", candidate, exc)
                google_results = []

            # Broad fallback for Latin names only
            broad_google = []
            if lang != "ar" and len(google_results) < min_results:
                try:
                    broad_google = await asyncio.wait_for(
                        fetch_google_books(candidate, max_results=20),
                        timeout=7.0,
                    )
                except asyncio.TimeoutError:
                    broad_google = []
                except Exception:
                    broad_google = []

            # OpenLibrary — only for Latin names (no Arabic support)
            ol_search = []
            ol_works = []
            if lang != "ar":
                try:
                    ol_search = await asyncio.wait_for(
                        fetch_openlibrary_books_by_author(candidate, limit=24),
                        timeout=18.0,
                    )
                except asyncio.TimeoutError:
                    pass
                except Exception as exc:
                    logger.warning("OpenLibrary search failed for '%s': %s", candidate, exc)

                if settings.ENABLE_OPENLIBRARY_AUTHOR_WORKS:
                    try:
                        ol_works = await asyncio.wait_for(
                            fetch_openlibrary_author_works(candidate, limit=30),
                            timeout=20.0,
                        )
                    except asyncio.TimeoutError:
                        pass
                    except Exception as exc:
                        logger.warning("OpenLibrary author-works failed for '%s': %s", candidate, exc)

            raw_items = _merge_unique_items(raw_items, google_results, broad_google, ol_search, ol_works)
            logger.info(
                "Candidate '%s' merged results: total=%s (google=%s, broad=%s, ol_search=%s, ol_works=%s)",
                candidate, len(raw_items), len(google_results), len(broad_google), len(ol_search), len(ol_works),
            )

            if len(raw_items) >= min_results:
                break

        if not raw_items:
            logger.error("NO raw items found for author '%s' from ANY source", name)
            return None

        # 4. Group editions into unique works
        grouped = enrichment_engine._group_editions(raw_items)
        logger.info("Grouped into %s unique works for author '%s'", len(grouped), name)

        # 5. Enrich each work into BookProfile
        profiles = []
        for work_data in grouped:
            try:
                profile = await enrichment_engine._create_book_profile(work_data)
                profiles.append(profile)
            except Exception as exc:
                logger.error("Failed to enrich work '%s': %s", work_data.get("title"), exc)
                continue

        # 6. Filter to books that actually match this author
        author_books = [b for b in profiles if _author_matches(b, name)]
        if not author_books:
            # Fallback: if strict filtering removes everything, use all results
            logger.warning("Strict author filter removed all books for '%s', using all %s results", name, len(profiles))
            author_books = profiles

        logger.info("Author '%s' matched %s books after filtering", name, len(author_books))

        # 7. Enrich author profile
        author_profile = await enrichment_engine.enrich_author(name, author_books)

        # 8. Cache results
        await AuthorService._cache_author(author_profile)
        await BookService._cache_books(author_books, f"author:{name}")

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
            # Try exact match first
            doc = await col.find_one({"author_id": _slugify(name)})
            if doc:
                return AuthorProfile(**doc)
            # Try name match
            doc = await col.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
            if doc:
                return AuthorProfile(**doc)
            # Try name variants
            doc = await col.find_one({"name_variants": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
            if doc:
                return AuthorProfile(**doc)
        except Exception as exc:
            logger.debug("Author cache lookup failed: %s", exc)
        return None

    @staticmethod
    async def _cache_author(profile: AuthorProfile) -> None:
        """Store author profile in cache."""
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

        # 2. Fetch books using small query variants with bounded per-query time.
        query_candidates = [f"{name} series", name]
        if "سلسلة" in name:
            stripped = " ".join(name.replace("سلسلة", " ").split())
            if stripped:
                query_candidates.append(stripped)

        books: List[BookProfile] = []
        for query_text in query_candidates:
            try:
                books = await asyncio.wait_for(
                    enrichment_engine.enrich_books_from_query(query_text, include_arabic=_is_arabic(name)),
                    timeout=8.0,
                )
                logger.info("Series query '%s' returned %s books", query_text, len(books))
                if books:
                    break
            except asyncio.TimeoutError:
                logger.warning("Series enrichment timed out for query: %s", query_text)

        # 4. Filter to actual series matches
        normalized_name = _normalize_lookup(name)
        series_books = [
            b for b in books
            if b.series_name and (normalized_name in _normalize_lookup(b.series_name) or _normalize_lookup(b.series_name) in normalized_name)
        ]
        logger.info("Series name filter: %s books match", len(series_books))

        # 5. Also include books where the title contains the series name
        if not series_books:
            series_books = [
                b for b in books
                if normalized_name in _normalize_lookup(b.title)
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