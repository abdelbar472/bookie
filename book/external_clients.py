"""
External API clients for book data aggregation
Google Books, OpenLibrary, Wikipedia
"""
import asyncio
import json
import re
import unicodedata
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import settings

logger = logging.getLogger(__name__)

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"


# ==================== TEXT UTILITIES ====================

def _is_arabic(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[\u0600-\u06FF]", text))


def _normalize_arabic(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return text.strip()


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"\b(el|al)[\s-]", "al-", normalized)
    normalized = re.sub(r"y\b", "i", normalized)
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[-\s]+", "-", normalized)
    return normalized or "unknown"


# ==================== WIKIPEDIA ====================

async def search_wikipedia(author_name: str, lang: str = "en") -> Optional[str]:
    """Search Wikipedia for author and return page title"""
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": author_name,
        "format": "json",
        "srlimit": 1
    }

    try:
        req = Request(f"{url}?{urlencode(params)}",
                      headers={"User-Agent": "BookieV3/1.0"})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = data.get("query", {}).get("search", [])
        return results[0]["title"] if results else None
    except Exception as e:
        logger.debug(f"Wikipedia search failed: {e}")
        return None


async def fetch_wikipedia_bio(title: str, lang: str) -> Optional[Dict]:
    """Fetch author bio from Wikipedia"""
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title.replace(' ', '_'))}"

    try:
        req = Request(url, headers={"User-Agent": "BookieV3/1.0"})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {
            "title": data.get("title"),
            "bio": data.get("extract"),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
            "image_url": data.get("thumbnail", {}).get("source") or data.get("originalimage", {}).get("source")
        }
    except Exception as e:
        logger.debug(f"Wikipedia fetch failed: {e}")
        return None


async def resolve_author(author_name: str) -> Dict[str, Any]:
    """Resolve author from Wikipedia (English and Arabic)"""
    author_name = (author_name or "").strip()
    is_arabic = _is_arabic(author_name)

    aliases = [author_name]
    best_bio = None

    # Run both language searches concurrently
    en_task = search_wikipedia(author_name, "en")
    ar_task = search_wikipedia(author_name, "ar")
    en_title, ar_title = await asyncio.gather(en_task, ar_task)

    titles_to_fetch = []
    if en_title:
        aliases.append(en_title)
        titles_to_fetch.append((en_title, "en"))
    if ar_title:
        aliases.append(ar_title)
        titles_to_fetch.append((ar_title, "ar"))

    # Expand aliases
    def _expand_aliases(name: str) -> List[str]:
        expanded = [name]
        low = name.lower()
        if "q" in low:
            expanded.append(name.replace("q", "k").replace("Q", "K"))
        if "k" in low:
            expanded.append(name.replace("k", "q").replace("K", "Q"))
        if " al-" in low.replace("el-", "al-"):
            expanded.append(name.replace(" al-", " "))
            expanded.append(name.replace(" al-", " el-"))
        return expanded

    aliases.extend([a for base in list(aliases) for a in _expand_aliases(base)])
    aliases = list(set(aliases))

    if titles_to_fetch:
        bio_tasks = [fetch_wikipedia_bio(t, l) for t, l in titles_to_fetch]
        bio_results = await asyncio.gather(*bio_tasks)

        for (t, l), bio_data in zip(titles_to_fetch, bio_results):
            if bio_data and not best_bio:
                best_bio = {
                    "author_id": _slugify(author_name),
                    "name": author_name,
                    "bio": bio_data.get("bio"),
                    "wikipedia_title": bio_data.get("title"),
                    "wikipedia_lang": l,
                    "wikipedia_url": bio_data.get("url"),
                    "image_url": bio_data.get("image_url"),
                }

    if best_bio:
        best_bio["aliases"] = list(set(aliases))
        return best_bio

    # Fallback
    return {
        "author_id": _slugify(author_name),
        "name": author_name,
        "bio": None,
        "wikipedia_title": None,
        "wikipedia_lang": "ar" if is_arabic else "en",
        "wikipedia_url": None,
        "image_url": None,
        "aliases": aliases,
    }


# ==================== GOOGLE BOOKS ====================

def _build_google_url(query: str, max_results: int, start_index: int = 0,
                      lang_restrict: Optional[str] = None) -> str:
    params = [
        f"q={quote_plus(query)}",
        f"maxResults={max(1, min(max_results, 40))}",
        f"startIndex={start_index}"
    ]
    if lang_restrict:
        params.append(f"langRestrict={quote_plus(lang_restrict)}")
    if settings.GOOGLE_BOOKS_API_KEY:
        params.append(f"key={quote_plus(settings.GOOGLE_BOOKS_API_KEY)}")
    return f"{GOOGLE_BOOKS_API}?{'&'.join(params)}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_json(url: str) -> Dict[str, Any]:
    req = Request(url, headers={"User-Agent": "bookie-v3/1.0"})
    with urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


async def fetch_google_books(query: str, max_results: int = 15, start_index: int = 0) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    url = _build_google_url(query=query, max_results=max_results, start_index=start_index)
    try:
        payload = await asyncio.to_thread(_fetch_json, url)
        items = payload.get("items") or []
        # Tag with source
        for item in items:
            item["_source"] = "google_books"
        return items
    except Exception as e:
        logger.warning(f"Google Books fetch failed: {e}")
        return []


async def fetch_arabic_books(query: str, max_results: int = 15, start_index: int = 0) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    normalized_query = _normalize_arabic(query)
    url = _build_google_url(query=normalized_query, max_results=max_results,
                            start_index=start_index, lang_restrict="ar")
    try:
        payload = await asyncio.to_thread(_fetch_json, url)
        items = payload.get("items") or []
        for item in items:
            item["_source"] = "google_books_arabic"
        return items
    except Exception as e:
        logger.warning(f"Arabic books fetch failed: {e}")
        return []


async def fetch_english_books(query: str, max_results: int = 15, start_index: int = 0) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    url = _build_google_url(query=query, max_results=max_results,
                            start_index=start_index, lang_restrict="en")
    try:
        payload = await asyncio.to_thread(_fetch_json, url)
        items = payload.get("items") or []
        for item in items:
            item["_source"] = "google_books_english"
        return items
    except Exception as e:
        logger.warning(f"English books fetch failed: {e}")
        return []


# ==================== OPENLIBRARY ====================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_openlibrary_books_by_author(author_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Fallback source when Google Books returns no useful items."""
    author_name = (author_name or "").strip()
    if not author_name:
        return []

    safe_limit = max(1, min(limit, 100))
    url = f"https://openlibrary.org/search.json?author={quote_plus(author_name)}&limit={safe_limit}"

    try:
        payload = await asyncio.to_thread(_fetch_json, url)
    except Exception as e:
        logger.warning(f"OpenLibrary author fetch failed: {e}")
        return []

    return _parse_openlibrary_docs(payload.get("docs", []), "openlibrary_author")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_openlibrary_books_by_title(title: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Fallback source for title search"""
    title = (title or "").strip()
    if not title:
        return []

    safe_limit = max(1, min(limit, 100))
    url = f"https://openlibrary.org/search.json?title={quote_plus(title)}&limit={safe_limit}"

    try:
        payload = await asyncio.to_thread(_fetch_json, url)
        if not payload.get("docs"):
            url_broad = f"https://openlibrary.org/search.json?q={quote_plus(title)}&limit={safe_limit}"
            payload = await asyncio.to_thread(_fetch_json, url_broad)
    except Exception as e:
        logger.warning(f"OpenLibrary title fetch failed: {e}")
        return []

    return _parse_openlibrary_docs(payload.get("docs", []), "openlibrary_title")


def _parse_openlibrary_docs(docs: List[Dict], source_tag: str) -> List[Dict[str, Any]]:
    """Parse OpenLibrary docs into Google Books-like format"""
    items = []
    for doc in docs:
        title = (doc.get("title") or "").strip()
        authors = [a for a in (doc.get("author_name") or []) if isinstance(a, str) and a.strip()]
        if not title or not authors:
            continue

        language = None
        languages = doc.get("language") or []
        if isinstance(languages, list) and languages:
            language = languages[0]

        year = doc.get("first_publish_year")
        published_date = str(year) if year else None

        items.append({
            "id": doc.get("key") or doc.get("cover_edition_key") or title,
            "_source": source_tag,
            "volumeInfo": {
                "title": title,
                "authors": authors,
                "publishedDate": published_date,
                "language": language,
                "categories": doc.get("subject", [])[:5],
                "description": None,
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": isbn}
                    for isbn in doc.get("isbn", [])[:1]
                ],
                "imageLinks": {},
                "pageCount": doc.get("number_of_pages_median"),
                "publisher": (doc.get("publisher") or [None])[0],
            },
        })
    return items