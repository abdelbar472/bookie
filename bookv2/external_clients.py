import httpx
import re
import unicodedata
import hashlib
import logging
from typing import Optional, List, Dict

from .config import settings

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": "bookv2-service/1.0 (contact: local-dev)",
    "Accept": "application/json",
}


def _slugify(name: str) -> str:
    """Create consistent author ID from name"""
    normalized = unicodedata.normalize("NFKC", name).lower().strip()
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[-\s]+", "-", normalized)
    if normalized:
        return normalized
    return hashlib.md5(name.encode()).hexdigest()[:10]


async def fetch_google_books(query: str, max_results: int = 10) -> List[Dict]:
    """Fetch books from Google Books API"""
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": query,
        "maxResults": max_results,
        "printType": "books",
        "projection": "full"
    }
    if settings.GOOGLE_BOOKS_API_KEY:
        params["key"] = settings.GOOGLE_BOOKS_API_KEY

    async with httpx.AsyncClient(headers=_DEFAULT_HEADERS) as client:
        resp = await client.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

    return data.get("items", [])


def normalize_book(raw_item: Dict) -> Optional[Dict]:
    """Normalize Google Books item to our schema"""
    volume = raw_item.get("volumeInfo", {})

    # Get ISBN
    identifiers = volume.get("industryIdentifiers", [])
    isbn = None
    for ident in identifiers:
        if ident.get("type") == "ISBN_13":
            isbn = ident.get("identifier")
            break
        elif ident.get("type") == "ISBN_10" and not isbn:
            isbn = ident.get("identifier")

    book_id = isbn or raw_item.get("id")
    if not book_id:
        return None

    authors = volume.get("authors", [])

    return {
        "book_id": book_id,
        "title": volume.get("title", "Unknown"),
        "authors": authors,
        "author_ids": [_slugify(a) for a in authors],
        "description": volume.get("description"),
        "categories": volume.get("categories", []),
        "thumbnail": volume.get("imageLinks", {}).get("thumbnail"),
        "published_date": volume.get("publishedDate"),
        "language": volume.get("language"),
        "average_rating": volume.get("averageRating"),
        "ratings_count": volume.get("ratingsCount"),
    }


async def search_wikipedia(author_name: str, lang: str = "en") -> Optional[str]:
    """Search Wikipedia and return first page title if found."""
    # OpenSearch is typically less strict than the query/search route.
    opensearch_url = f"https://{lang}.wikipedia.org/w/api.php"
    opensearch_params = {
        "action": "opensearch",
        "search": author_name,
        "limit": 1,
        "namespace": 0,
        "format": "json",
    }

    open_search_data = None
    try:
        async with httpx.AsyncClient(headers=_DEFAULT_HEADERS) as client:
            resp = await client.get(opensearch_url, params=opensearch_params, timeout=10)
            resp.raise_for_status()
            open_search_data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Wikipedia opensearch failed for '%s' (%s): %s", author_name, lang, exc)
        open_search_data = None

    if isinstance(open_search_data, list) and len(open_search_data) >= 2:
        suggestions = open_search_data[1]
        if isinstance(suggestions, list) and suggestions:
            return str(suggestions[0])

    # Fallback to regular search API.
    search_url = f"https://{lang}.wikipedia.org/w/api.php"
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": author_name,
        "format": "json",
        "srlimit": 1,
    }

    try:
        async with httpx.AsyncClient(headers=_DEFAULT_HEADERS) as client:
            resp = await client.get(search_url, params=search_params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Wikipedia title lookup failed for '%s' (%s): %s", author_name, lang, exc)
        return None

    results = data.get("query", {}).get("search", [])
    if results:
        return results[0]["title"]
    return None


def _extract_author_from_summary(description: str) -> Optional[str]:
    if not description:
        return None

    # Examples: "novel by George Orwell", "book by Yuval Noah Harari"
    match = re.search(r"\bby\s+([^,.;()]+)", description, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


async def resolve_book_from_wikipedia(title: str) -> Optional[Dict]:
    """Resolve a book title from Wikipedia and return normalized book-like payload."""
    for lang in ["en", "ar"]:
        page_title = await search_wikipedia(title, lang)
        if not page_title:
            continue

        summary = await fetch_wikipedia_bio(page_title, lang)
        if not summary:
            continue

        inferred_author = _extract_author_from_summary(summary.get("bio") or "")
        authors = [inferred_author] if inferred_author else []

        return {
            "book_id": f"wiki:{_slugify(page_title)}",
            "title": summary.get("title") or title,
            "authors": authors,
            "author_ids": [_slugify(a) for a in authors],
            "description": summary.get("bio") or "",
            "categories": [],
            "thumbnail": None,
            "published_date": None,
            "language": lang,
            "average_rating": None,
            "ratings_count": None,
            "source": "wikipedia",
        }

    return None


async def fetch_wikipedia_bio(title: str, lang: str) -> Optional[Dict]:
    """Fetch author bio from Wikipedia"""
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"

    try:
        async with httpx.AsyncClient(headers=_DEFAULT_HEADERS) as client:
            resp = await client.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Wikipedia bio fetch failed for '%s' (%s): %s", title, lang, exc)
        return None

    return {
        "title": data.get("title"),
        "bio": data.get("extract"),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
        "lang": lang
    }


async def resolve_author(author_name: str) -> Optional[Dict]:
    """
    Resolve author name to Wikipedia page.
    Try English first, fallback to Arabic.
    """
    for lang in ["en", "ar"]:
        title = await search_wikipedia(author_name, lang)
        if title:
            bio_data = await fetch_wikipedia_bio(title, lang)
            if bio_data:
                return {
                    "author_id": _slugify(author_name),
                    "name": author_name,
                    "bio": bio_data["bio"],
                    "wikipedia_title": bio_data["title"],
                    "wikipedia_lang": lang,
                    "wikipedia_url": bio_data["url"],
                }
    return None