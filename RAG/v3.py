#!/usr/bin/env python3
"""
Book Recommendation System - V3 (Multi-language Support)
Searches database first, then Google API, supports Arabic/English/any language.
"""

import asyncio
import logging
import os
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer


# ============================================================
# CONFIGURATION - Check API keys at startup
# ============================================================


def _load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = value.strip().strip('"').strip("'")


def _bootstrap_env() -> None:
    current_dir = Path(__file__).resolve().parent
    workspace_root = current_dir.parent

    # Precedence: existing process env > RAG/.env > workspace .env
    _load_env_file(current_dir / ".env")
    _load_env_file(workspace_root / ".env")


_bootstrap_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
COLLECTION_NAME = "books"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip()
QDRANT_LOCAL_PATH = os.getenv("QDRANT_LOCAL_PATH", str(Path(__file__).resolve().parent / "qdrant_local"))
GOOGLE_TIMEOUT_SECONDS = 15
GOOGLE_MAX_RETRIES = 3

# Validate API key
HAS_GOOGLE_API = bool(GOOGLE_API_KEY and GOOGLE_API_KEY not in ["", "your_key_here", "your_api_key_here", "AIzaSy..."])

print("🔧 Loading embedding model...")
encoder = SentenceTransformer("all-MiniLM-L6-v2")
VECTOR_SIZE = encoder.get_sentence_embedding_dimension()
print(f"✅ Ready! Vector size: {VECTOR_SIZE}")

if HAS_GOOGLE_API:
    print("✅ Google API key detected - external search enabled")
else:
    print("⚠️  No Google API Key detected - external search disabled")
    print("   Set with: set GOOGLE_API_KEY=your_actual_key")


_ARABIC_DIACRITICS_PATTERN = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")


# ============================================================
# NORMALIZATION / UTILS
# ============================================================


def normalize_text(value: str) -> str:
    """Normalize text for language-agnostic comparisons (including Arabic)."""
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = _ARABIC_DIACRITICS_PATTERN.sub("", normalized)
    return normalized.casefold().strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _book_embed_text(book: Dict[str, Any]) -> str:
    categories = book.get("categories") or []
    return (
        f"Title: {book.get('title', '')}. "
        f"Author: {book.get('authors', '')}. "
        f"Description: {book.get('description', '')}. "
        f"Genres: {', '.join(categories)}."
    )


def _author_embed_text(book: Dict[str, Any]) -> str:
    categories = book.get("categories") or []
    return f"Author: {book.get('authors', '')}. Genres: {', '.join(categories)}."


def _iter_scroll_pages(
    client: QdrantClient,
    *,
    scroll_filter: Optional[models.Filter] = None,
    page_size: int = 128,
    with_payload: bool = True,
    with_vectors: bool = False,
    max_points: int = 2048,
) -> Iterator[Any]:
    """Iterate through Qdrant scroll pages to avoid loading full collection in memory."""
    offset = None
    yielded = 0

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=scroll_filter,
            limit=page_size,
            offset=offset,
            with_payload=with_payload,
            with_vectors=with_vectors,
        )

        if not points:
            break

        for point in points:
            yield point
            yielded += 1
            if yielded >= max_points:
                return

        if next_offset is None:
            break

        offset = next_offset


# ============================================================
# QDRANT CONNECTION
# ============================================================


def get_client() -> QdrantClient:
    """Create a Qdrant client instance (no global singleton)."""
    try:
        if QDRANT_API_KEY:
            client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY)
        else:
            client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        client.get_collections()
        logger.info("Connected to Qdrant at %s:%s", QDRANT_HOST, QDRANT_PORT)
        return client
    except Exception as remote_error:
        logger.warning(
            "Remote Qdrant unavailable (%s). Falling back to local storage: %s",
            remote_error,
            QDRANT_LOCAL_PATH,
        )
        try:
            os.makedirs(QDRANT_LOCAL_PATH, exist_ok=True)
            client = QdrantClient(path=QDRANT_LOCAL_PATH)
            logger.info("Using local Qdrant path: %s", QDRANT_LOCAL_PATH)
            return client
        except Exception as local_error:
            raise RuntimeError(f"Failed to initialize both remote and local Qdrant. Local error: {local_error}")


def close_client(client: Optional[QdrantClient]) -> None:
    """Close a Qdrant client safely."""
    if client is None:
        return
    try:
        client.close()
    except Exception as exc:
        logger.debug("Failed to close Qdrant client cleanly: %s", exc)


def get_next_id() -> str:
    """Generate collision-safe IDs for concurrent writes."""
    return str(uuid.uuid4())


# ============================================================
# DATABASE SEARCH (Multi-language support)
# ============================================================


def search_database(client: QdrantClient, query: str) -> List[Dict[str, Any]]:
    """Search database for books matching query (supports any language)."""
    try:
        query_norm = normalize_text(query)
        if not query_norm:
            return []

        exact_filter = models.Filter(
            should=[
                models.FieldCondition(key="normalized_title", match=models.MatchValue(value=query_norm)),
                models.FieldCondition(key="title", match=models.MatchValue(value=query.strip())),
            ]
        )
        fuzzy_filter = models.Filter(
            should=[
                models.FieldCondition(key="normalized_title", match=models.MatchText(text=query_norm)),
                models.FieldCondition(key="normalized_authors", match=models.MatchText(text=query_norm)),
                models.FieldCondition(key="normalized_description", match=models.MatchText(text=query_norm)),
            ]
        )

        candidates: List[Any] = []
        seen_ids = set()

        try:
            for point in _iter_scroll_pages(client, scroll_filter=exact_filter, page_size=64, max_points=128):
                if point.id in seen_ids:
                    continue
                candidates.append(point)
                seen_ids.add(point.id)
        except Exception as exc:
            logger.warning("Exact filter search failed, continuing with fuzzy search: %s", exc)

        try:
            for point in _iter_scroll_pages(client, scroll_filter=fuzzy_filter, page_size=64, max_points=512):
                if point.id in seen_ids:
                    continue
                candidates.append(point)
                seen_ids.add(point.id)
        except Exception as exc:
            logger.warning("Fuzzy filter search failed, falling back to paginated scan: %s", exc)
            for point in _iter_scroll_pages(client, page_size=128, max_points=1024):
                if point.id in seen_ids:
                    continue
                candidates.append(point)
                seen_ids.add(point.id)

        matches: List[Dict[str, Any]] = []
        for book in candidates:
            payload = book.payload or {}
            title_raw = str(payload.get("title", ""))
            authors_raw = str(payload.get("authors", ""))
            description_raw = str(payload.get("description", ""))

            title = normalize_text(str(payload.get("normalized_title", title_raw)))
            authors = normalize_text(str(payload.get("normalized_authors", authors_raw)))
            description = normalize_text(str(payload.get("normalized_description", description_raw)))

            if query_norm == title:
                matches.append({"book": book, "match_type": "exact", "score": 1.0})
            elif query_norm in title:
                matches.append({"book": book, "match_type": "title", "score": 0.9})
            elif title in query_norm and len(title) > 3:
                matches.append({"book": book, "match_type": "partial", "score": 0.8})
            elif query_norm in authors:
                matches.append({"book": book, "match_type": "author", "score": 0.7})
            elif query_norm in description and len(query_norm) > 4:
                matches.append({"book": book, "match_type": "description", "score": 0.6})

        if not matches and len(query) > 2:
            try:
                query_vec = encoder.encode(query).tolist()
                try:
                    semantic_results = client.query_points(
                        collection_name=COLLECTION_NAME,
                        query=query_vec,
                        using="book_content",
                        limit=5,
                        with_payload=True,
                    ).points
                except Exception:
                    # Compatibility path for older single-vector collections.
                    semantic_results = client.query_points(
                        collection_name=COLLECTION_NAME,
                        query=query_vec,
                        limit=5,
                        with_payload=True,
                    ).points

                for hit in semantic_results:
                    if hit.score > 0.65:
                        matches.append({"book": hit, "match_type": "semantic", "score": hit.score})
            except Exception as exc:
                logger.warning("Semantic search failed for query '%s': %s", query, exc)

        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches

    except Exception as exc:
        logger.exception("Database search failed for query '%s': %s", query, exc)
        return []


# ============================================================
# GOOGLE BOOKS API (Multi-language support)
# ============================================================


async def search_google_books_async(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search Google Books API - supports any language including Arabic."""
    if not HAS_GOOGLE_API:
        return []

    url = "https://www.googleapis.com/books/v1/volumes"

    search_queries = [
        query,
        f'intitle:"{query}"',
    ]

    all_books: List[Dict[str, Any]] = []
    seen_ids = set()

    async with httpx.AsyncClient(timeout=GOOGLE_TIMEOUT_SECONDS) as http_client:
        for search_query in search_queries:
            if len(all_books) >= max_results:
                break

            params = {
                "q": search_query,
                "key": GOOGLE_API_KEY,
                "maxResults": max_results,
                "printType": "books",
                "orderBy": "relevance",
            }

            try:
                data = None
                for attempt in range(1, GOOGLE_MAX_RETRIES + 1):
                    await asyncio.sleep(0.4)
                    response = await http_client.get(url, params=params)

                    if response.status_code == 429:
                        wait_seconds = min(2 ** attempt, 8)
                        logger.warning(
                            "Google Books rate limited for '%s', retrying in %ss (%s/%s)",
                            search_query,
                            wait_seconds,
                            attempt,
                            GOOGLE_MAX_RETRIES,
                        )
                        await asyncio.sleep(wait_seconds)
                        continue

                    if response.status_code == 403:
                        logger.error("Google Books API key invalid or quota exceeded")
                        return []

                    if response.status_code != 200:
                        logger.warning(
                            "Google Books returned status %s for query '%s'",
                            response.status_code,
                            search_query,
                        )
                        break

                    data = response.json()
                    break

                if not data:
                    continue

                for item in data.get("items", []):
                    book_id = item.get("id")
                    if book_id in seen_ids:
                        continue
                    seen_ids.add(book_id)

                    volume = item.get("volumeInfo", {})
                    authors = volume.get("authors", ["Unknown"])
                    categories = volume.get("categories", [])
                    language = volume.get("language", "unknown")

                    book = {
                        "id": book_id,
                        "title": volume.get("title", "Unknown"),
                        "authors": ", ".join(authors),
                        "description": volume.get("description", "")[:800],
                        "categories": categories,
                        "published_date": volume.get("publishedDate", "Unknown"),
                        "page_count": volume.get("pageCount", 0) or 0,
                        "average_rating": volume.get("averageRating", 0) or 0,
                        "ratings_count": volume.get("ratingsCount", 0) or 0,
                        "language": language,
                        "thumbnail": volume.get("imageLinks", {}).get("thumbnail", ""),
                        "preview_link": volume.get("previewLink", ""),
                        "publisher": volume.get("publisher", ""),
                        "source": "google_books",
                    }

                    book["embed_text"] = _book_embed_text(book)
                    book["author_text"] = _author_embed_text(book)

                    all_books.append(book)
                    if len(all_books) >= max_results:
                        break

            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Google Books lookup failed for query '%s': %s", search_query, exc)

    return all_books


def search_google_books(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Sync wrapper for CLI usage."""
    return asyncio.run(search_google_books_async(query, max_results=max_results))


# ============================================================
# ADD BOOK TO DATABASE
# ============================================================


def add_book_to_database(client: QdrantClient, book: Dict[str, Any]) -> str:
    """Add new book to database."""
    new_id = get_next_id()

    categories = book.get("categories") or []
    if not book.get("embed_text"):
        book["embed_text"] = _book_embed_text(book)
    if not book.get("author_text"):
        book["author_text"] = _author_embed_text(book)

    # Cache vectors on the book object to avoid duplicate re-encoding.
    book_vec = book.get("_book_vec")
    if not book_vec:
        book_vec = encoder.encode(book["embed_text"]).tolist()
        book["_book_vec"] = book_vec

    author_vec = book.get("_author_vec")
    if not author_vec:
        author_vec = encoder.encode(book["author_text"]).tolist()
        book["_author_vec"] = author_vec

    point = PointStruct(
        id=new_id,
        vector={
            "book_content": book_vec,
            "author_style": author_vec,
        },
        payload={
            "title": book.get("title", "Unknown"),
            "authors": book.get("authors", "Unknown"),
            "author_name": book.get("authors", "Unknown").split(",")[0].strip(),
            "description": str(book.get("description", ""))[:500],
            "categories": categories,
            "published_date": book.get("published_date", "Unknown"),
            "page_count": _safe_int(book.get("page_count", 0)),
            "average_rating": _safe_float(book.get("average_rating", 0)),
            "ratings_count": _safe_int(book.get("ratings_count", 0)),
            "language": book.get("language", "unknown"),
            "thumbnail": book.get("thumbnail", ""),
            "preview_link": book.get("preview_link", ""),
            "source": book.get("source", "google_books"),
            "normalized_title": normalize_text(str(book.get("title", ""))),
            "normalized_authors": normalize_text(str(book.get("authors", ""))),
            "normalized_description": normalize_text(str(book.get("description", ""))),
        },
    )

    client.upsert(collection_name=COLLECTION_NAME, points=[point])
    return new_id


# ============================================================
# FIND SIMILAR BOOKS
# ============================================================


def find_similar_books(client: QdrantClient, target_book: Any, limit: int = 5):
    """Find similar books using both vectors."""
    if hasattr(target_book, "vector"):
        vector_data = target_book.vector or {}
        if isinstance(vector_data, dict):
            book_vec = vector_data.get("book_content")
            author_vec = vector_data.get("author_style")
        else:
            book_vec = vector_data
            author_vec = vector_data
        target_id = target_book.id
    else:
        book_vec = target_book.get("_book_vec")
        author_vec = target_book.get("_author_vec")

        if not book_vec:
            embed_text = target_book.get("embed_text") or _book_embed_text(target_book)
            book_vec = encoder.encode(embed_text).tolist()
            target_book["_book_vec"] = book_vec

        if not author_vec:
            author_text = target_book.get("author_text") or _author_embed_text(target_book)
            author_vec = encoder.encode(author_text).tolist()
            target_book["_author_vec"] = author_vec

        target_id = None

    if not book_vec:
        return []

    try:
        content_res = client.query_points(
            collection_name=COLLECTION_NAME,
            query=book_vec,
            using="book_content",
            limit=limit + 5,
            with_payload=True,
        ).points
    except Exception as exc:
        logger.warning("Named vector query failed (book_content), trying fallback: %s", exc)
        try:
            content_res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=book_vec,
                limit=limit + 5,
                with_payload=True,
            ).points
        except Exception as fallback_exc:
            logger.error("Fallback similarity query failed: %s", fallback_exc)
            return []

    try:
        author_res = client.query_points(
            collection_name=COLLECTION_NAME,
            query=author_vec or book_vec,
            using="author_style",
            limit=limit + 5,
            with_payload=True,
        ).points
    except Exception as exc:
        logger.warning("Named vector query failed (author_style): %s", exc)
        author_res = []

    merged: Dict[Any, Dict[str, Any]] = {}

    for hit in content_res:
        if target_id is None or hit.id != target_id:
            merged[hit.id] = {"hit": hit, "score": hit.score * 0.6}

    for hit in author_res:
        if target_id is None or hit.id != target_id:
            if hit.id in merged:
                merged[hit.id]["score"] += hit.score * 0.4
            else:
                merged[hit.id] = {"hit": hit, "score": hit.score * 0.4}

    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)

    results = []
    for item in ranked[:limit]:
        item["hit"].score = item["score"]
        results.append(item["hit"])

    return results


def suggest_local_books_from_query(client: QdrantClient, query: str, limit: int = 5):
    """Return best-effort local semantic suggestions for a free-text query."""
    try:
        query_vec = encoder.encode(query).tolist()
    except Exception as exc:
        logger.warning("Failed to encode local suggestion query '%s': %s", query, exc)
        return []

    try:
        hits = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vec,
            using="book_content",
            limit=limit,
            with_payload=True,
        ).points
    except Exception as exc:
        logger.warning("Named vector suggestions failed, trying fallback: %s", exc)
        try:
            hits = client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vec,
                limit=limit,
                with_payload=True,
            ).points
        except Exception as fallback_exc:
            logger.error("Fallback suggestion query failed: %s", fallback_exc)
            return []

    return hits


def search_books_by_writer(client: QdrantClient, writer_query: str, limit: int = 20):
    """Search local database by writer/author name using filter + pagination."""
    writer_input = writer_query.strip()
    writer_norm = normalize_text(writer_input)
    if not writer_norm:
        return []

    writer_filter = models.Filter(
        should=[
            models.FieldCondition(key="normalized_authors", match=models.MatchText(text=writer_norm)),
            models.FieldCondition(key="authors", match=models.MatchText(text=writer_input)),
        ]
    )

    matches = []
    try:
        iterator = _iter_scroll_pages(
            client,
            scroll_filter=writer_filter,
            page_size=64,
            max_points=max(limit * 8, 256),
        )
    except Exception as exc:
        logger.warning("Writer filter query failed, falling back to paginated scan: %s", exc)
        iterator = _iter_scroll_pages(client, page_size=128, max_points=2048)

    for book in iterator:
        payload = book.payload or {}
        authors = normalize_text(str(payload.get("normalized_authors", payload.get("authors", ""))))
        if writer_norm in authors:
            categories = payload.get("categories") or []
            rating = _safe_float(payload.get("average_rating", 0))
            matches.append(
                {
                    "book": book,
                    "sort_key": (
                        1 if writer_norm == authors else 0,
                        rating,
                        len(categories),
                    ),
                }
            )

    matches.sort(key=lambda item: item["sort_key"], reverse=True)
    return [m["book"] for m in matches[:limit]]


# ============================================================
# SETUP / SEED DATA
# ============================================================


def setup_database(client: QdrantClient):
    """Setup initial database."""
    cols = client.get_collections()
    if COLLECTION_NAME in [c.name for c in cols.collections]:
        has_malek_count = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=models.Filter(
                should=[
                    models.FieldCondition(key="normalized_title", match=models.MatchValue(value=normalize_text("مالك الحزين"))),
                    models.FieldCondition(key="title", match=models.MatchValue(value="مالك الحزين")),
                ]
            ),
            exact=False,
        ).count
        if has_malek_count == 0:
            book = {
                "title": "مالك الحزين",
                "authors": "إبراهيم أصلان",
                "description": "رواية مصرية واقعية تدور حول الحياة اليومية في حي شعبي في القاهرة.",
                "categories": ["أدب عربي", "رواية واقعية"],
                "published_date": "1983",
                "page_count": 190,
                "average_rating": 4.0,
                "language": "ar",
                "source": "seed",
            }
            add_book_to_database(client, book)
            logger.info("Added missing seed: مالك الحزين")
        return

    logger.info("Creating collection: %s", COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "book_content": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            "author_style": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        },
    )

    seed_books = [
        {"title": "Dune", "authors": "Frank Herbert", "description": "Epic sci-fi about politics and ecology on desert planet Arrakis.", "categories": ["Science Fiction"], "published_date": "1965", "page_count": 412, "average_rating": 4.3, "language": "en"},
        {"title": "1984", "authors": "George Orwell", "description": "Dystopian novel about surveillance and totalitarianism.", "categories": ["Dystopian"], "published_date": "1949", "page_count": 328, "average_rating": 4.2, "language": "en"},
        {"title": "Neuromancer", "authors": "William Gibson", "description": "Cyberpunk classic with AI and hackers.", "categories": ["Cyberpunk"], "published_date": "1984", "page_count": 271, "average_rating": 3.9, "language": "en"},
        {"title": "Foundation", "authors": "Isaac Asimov", "description": "Mathematical sociology predicts fall of galactic empires.", "categories": ["Science Fiction"], "published_date": "1951", "page_count": 244, "average_rating": 4.2, "language": "en"},
        {"title": "The Left Hand of Darkness", "authors": "Ursula K. Le Guin", "description": "Exploration of gender on alien world.", "categories": ["Science Fiction"], "published_date": "1969", "page_count": 304, "average_rating": 4.1, "language": "en"},
        {"title": "أرض زيكولا", "authors": "عمرو عبدالحميد", "description": "رواية خيال علمي عربية عن عالم زيكولا المسحور", "categories": ["خيال علمي", "أدب عربي"], "published_date": "2016", "page_count": 320, "average_rating": 4.1, "language": "ar"},
        {"title": "مالك الحزين", "authors": "إبراهيم أصلان", "description": "رواية مصرية واقعية تدور حول الحياة اليومية في حي شعبي في القاهرة.", "categories": ["أدب عربي", "رواية واقعية"], "published_date": "1983", "page_count": 190, "average_rating": 4.0, "language": "ar"},
    ]

    for book in seed_books:
        book["source"] = "seed"
        add_book_to_database(client, book)

    logger.info("Added %s seed books (English + Arabic)", len(seed_books))


# ============================================================
# CLI FLOW
# ============================================================


def run_writer_search(client: QdrantClient, writer_query: str):
    """Run writer-first search flow, then recommend from selected book."""
    print(f"\n🔎 WRITER SEARCH: '{writer_query}'")
    author_books = search_books_by_writer(client, writer_query, limit=20)

    if not author_books:
        print("   ❌ No books found for this writer in local database")
        fallback = suggest_local_books_from_query(client, writer_query, limit=5)
        if fallback:
            print("\n📚 Closest local matches:")
            print("=" * 60)
            for i, hit in enumerate(fallback, 1):
                p = hit.payload or {}
                print(f"\n{i}. 📖 {p.get('title', 'Unknown')}")
                if p.get("authors"):
                    print(f"   ✍️  {p['authors']}")
                print(f"   📊 Similarity: {hit.score:.3f}")
        return None

    print(f"   ✅ Found {len(author_books)} book(s) by this writer:")
    print("=" * 60)
    for i, book in enumerate(author_books, 1):
        p = book.payload or {}
        print(f"\n{i}. 📖 {p.get('title', 'Unknown')}")
        if p.get("authors"):
            print(f"   ✍️  {p['authors']}")
        if p.get("average_rating"):
            print(f"   ⭐ {p['average_rating']}/5")

    selected = author_books[0]
    if len(author_books) > 1:
        try:
            choice = input(f"\nSelect a book (1-{len(author_books)}) or press Enter for 1: ").strip()
            if choice:
                idx = int(choice) - 1
                if 0 <= idx < len(author_books):
                    selected = author_books[idx]
        except ValueError:
            pass

    print("\n🔍 Finding recommendations from selected writer book...")
    recommendations = find_similar_books(client, selected, limit=5)

    if recommendations:
        print("\n📚 TOP 5 RECOMMENDATIONS:")
        print("=" * 60)
        for i, hit in enumerate(recommendations, 1):
            rp = hit.payload or {}
            print(f"\n{i}. 📖 {rp.get('title', 'Unknown')}")
            if rp.get("authors"):
                print(f"   ✍️  {rp['authors']}")
            print(f"   📊 Match Score: {hit.score:.3f}")

    return recommendations


def get_recommendations(client: QdrantClient, user_query: str):
    """Main recommendation flow."""
    print(f"\n🔍 STEP 1: Searching database for '{user_query}'...")
    db_matches = search_database(client, user_query)

    if db_matches:
        best_match = db_matches[0]
        book = best_match["book"]
        print("   ✅ FOUND in database!")
        print(f"   📖 Match: {book.payload['title']}")
        target_book = book
    else:
        print("   ❌ NOT found in database")

        if not HAS_GOOGLE_API:
            print("\n❌ Cannot search external APIs - no Google API key")
            fallback = suggest_local_books_from_query(client, user_query, limit=5)
            if fallback:
                print("\n📚 Closest books in local database:")
                print("=" * 60)
                for i, hit in enumerate(fallback, 1):
                    p = hit.payload or {}
                    print(f"\n{i}. 📖 {p.get('title', 'Unknown')}")
                    print(f"   📊 Similarity: {hit.score:.3f}")
            return None

        print("\n🔍 STEP 2: Searching Google Books API...")
        api_results = search_google_books(user_query, max_results=5)
        if not api_results:
            print("   ❌ No results from Google Books API")
            return None

        selected = api_results[0]
        print(f"\n💾 STEP 3: Adding to database... {selected['title']}")
        new_id = add_book_to_database(client, selected)
        print(f"   ✅ Added with ID: {new_id}")
        target_book = selected

    print("\n🔍 STEP 4: Finding similar books...")
    recommendations = find_similar_books(client, target_book, limit=5)

    if recommendations:
        print("\n📚 TOP 5 RECOMMENDATIONS:")
        print("=" * 60)
        for i, hit in enumerate(recommendations, 1):
            p = hit.payload
            print(f"\n{i}. 📖 {p['title']}")
            if p.get("authors"):
                print(f"   ✍️  {p['authors']}")
            print(f"   📊 Match Score: {hit.score:.3f}")

    return recommendations


def main():
    """Main loop."""
    print("\n" + "=" * 70)
    print("📚 SMART BOOK RECOMMENDER V3")
    print("   Multi-language support (English, Arabic, any language)")
    print("=" * 70)

    try:
        client = get_client()
    except Exception as err:
        print(f"\n❌ Startup failed: {err}")
        return

    setup_database(client)

    try:
        total = client.count(collection_name=COLLECTION_NAME, exact=False).count
        print(f"\n📊 Database: {total} books")
        if not HAS_GOOGLE_API:
            print("⚠️  External search disabled (no API key)")
    except Exception as exc:
        logger.warning("Failed to fetch database count: %s", exc)

    try:
        while True:
            print("\n" + "=" * 70)
            print("Enter a book title or search by writer")
            print("Examples: 'Dune', 'مالك الحزين', 'writer: Frank Herbert'")
            print("=" * 70)

            query = input("\n📖 Book title (or 'quit'): ").strip()
            if not query:
                continue

            if query.lower() in ["quit", "exit", "q"]:
                print("\n👋 Goodbye!")
                break

            if query.lower().startswith("writer:") or query.lower().startswith("author:"):
                writer_query = query.split(":", 1)[1].strip() if ":" in query else ""
                if not writer_query:
                    print("   ⚠️  Please add writer name, e.g. writer: Frank Herbert")
                    continue
                run_writer_search(client, writer_query)
            else:
                get_recommendations(client, query)

            try:
                total = client.count(collection_name=COLLECTION_NAME, exact=False).count
                print(f"\n📊 Database now has {total} books")
            except Exception as exc:
                logger.warning("Failed to fetch updated database count: %s", exc)
    except (KeyboardInterrupt, EOFError):
        print("\n\n👋 Stopped by user.")
    finally:
        close_client(client)


if __name__ == "__main__":
    main()

