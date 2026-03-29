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
    """Search Wikipedia for author, return page title if found"""
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": author_name,
        "format": "json",
        "srlimit": 1
    }

    try:
        async with httpx.AsyncClient(headers=_DEFAULT_HEADERS) as client:
            resp = await client.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Wikipedia title lookup failed for '%s' (%s): %s", author_name, lang, exc)
        return None

    results = data.get("query", {}).get("search", [])
    if results:
        return results[0]["title"]
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