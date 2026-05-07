"""
External API clients — Fixed V4
Resolve name → Search APIs → Return results
Language-aware routing with robust error handling
"""
import asyncio
import json
import re
import unicodedata
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import settings

logger = logging.getLogger(__name__)

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"


# ==================== LANGUAGE DETECTION ====================

def detect_language(text: str) -> str:
    """Detect if text is Arabic, English, or unknown."""
    if not text:
        return "unknown"
    if bool(re.search(r"[؀-ۿ]", text)):
        return "ar"
    alpha_chars = [c for c in text if c.isalpha()]
    if alpha_chars and all(c.isascii() for c in alpha_chars):
        return "en"
    return "unknown"

def _is_arabic(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[؀-ۿ]", text))


def _normalize_arabic(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[ً-ٰٟۖ-ۭـ]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return text.strip()


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[-\s]+", "-", normalized)
    return normalized or "unknown"


# ==================== NAME RESOLUTION ====================

def build_author_name_variants(name: str) -> List[str]:
    variants = {name}
    lower = name.lower()
    swaps = [
        ("q", "k"), ("gh", "g"), ("kh", "h"), ("th", "t"),
        ("dh", "d"), ("sh", "ch"), ("ou", "u"), ("oo", "u"),
        ("aa", "a"), ("ee", "i"), ("el-", "al-"), ("abd", "abdel"),
    ]
    for a, b in swaps:
        if a in lower:
            variants.add(name.lower().replace(a, b).title())
        if b in lower:
            variants.add(name.lower().replace(b, a).title())
    for v in list(variants):
        v_lower = v.lower()
        if " al " in v_lower:
            variants.add(v_lower.replace(" al ", " al-").title())
        if " al-" in v_lower:
            variants.add(v_lower.replace(" al-", " al ").title())
    return list(variants)


async def resolve_author_names(name: str) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        return {"primary": "", "variants": [], "lang": "unknown", "arabic_names": [], "latin_names": []}
    lang = detect_language(name)
    arabic_names = []
    latin_names = []
    variants = [name]
    if lang == "ar":
        arabic_names.append(name)
        trans = _normalize_arabic(name)
        trans_map = str.maketrans(
            "ابتثجحخدذرزسشصضطظعغفقكلمنهويأإآؤئىة",
            "abtthjhkhdhrdhzsshdtz'ghfqklmnhwyaaa'iyh"
        )
        latin = trans.translate(trans_map)
        latin = re.sub(r"[^\w\s]", "", latin).strip()
        if latin and latin != name:
            latin_names.append(latin)
            variants.append(latin)
    else:
        latin_names.append(name)
        for v in build_author_name_variants(name):
            if v not in latin_names:
                latin_names.append(v)
                variants.append(v)
    return {
        "primary": name,
        "variants": list(dict.fromkeys(variants)),
        "lang": lang,
        "arabic_names": arabic_names,
        "latin_names": latin_names,
    }


# ==================== WIKIPEDIA (FIXED) ====================

async def search_wikipedia(query: str, lang: str = "en") -> Optional[str]:
    """Search Wikipedia and return page title."""
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 3,
    }
    try:
        req = Request(f"{url}?{urlencode(params)}", headers={"User-Agent": "BookieV4/1.0"})
        def fetch():
            with urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        data = await asyncio.to_thread(fetch)
        results = data.get("query", {}).get("search", [])
        return results[0]["title"] if results else None
    except Exception as e:
        logger.debug("Wikipedia search failed: %s", e)
        return None


async def fetch_wikipedia_page(title: str, lang: str) -> Optional[Dict]:
    """Fetch page data from Wikipedia using REST API."""
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title.replace(' ', '_'))}"
    try:
        req = Request(url, headers={"User-Agent": "BookieV4/1.0"})
        def fetch():
            with urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        data = await asyncio.to_thread(fetch)
        return {
            "title": data.get("title"),
            "bio": data.get("extract"),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
            "image_url": data.get("thumbnail", {}).get("source") or data.get("originalimage", {}).get("source"),
        }
    except HTTPError as e:
        if e.code == 404:
            logger.debug("Wikipedia page not found: %s", title)
        else:
            logger.debug("Wikipedia bio failed: %s", e)
        return None
    except Exception as e:
        logger.debug("Wikipedia bio failed: %s", e)
        return None


async def resolve_author(author_name: str) -> Dict[str, Any]:
    """Resolve author: search Wikipedia in detected language + fallback."""
    author_name = (author_name or "").strip()
    lang = detect_language(author_name)
    aliases = [author_name]
    best_bio = None

    search_order = [lang, "en" if lang == "ar" else "ar"] if lang != "unknown" else ["en", "ar"]

    for search_lang in search_order:
        title = await search_wikipedia(author_name, search_lang)
        if title:
            aliases.append(title)
            bio = await fetch_wikipedia_page(title, search_lang)
            if bio and bio.get("bio"):
                best_bio = {
                    "author_id": _slugify(author_name),
                    "name": author_name,
                    "bio": bio.get("bio"),
                    "wikipedia_title": bio.get("title"),
                    "wikipedia_lang": search_lang,
                    "wikipedia_url": bio.get("url"),
                    "image_url": bio.get("image_url"),
                }
                break

    if best_bio:
        best_bio["aliases"] = list(set(aliases))
        return best_bio

    return {
        "author_id": _slugify(author_name),
        "name": author_name,
        "bio": None,
        "wikipedia_title": None,
        "wikipedia_lang": lang if lang != "unknown" else "en",
        "wikipedia_url": None,
        "image_url": None,
        "aliases": aliases,
    }


async def resolve_book_wikipedia(title: str, author: Optional[str] = None, lang: str = "en") -> Optional[Dict]:
    """Search Wikipedia for a book with multiple query strategies."""
    queries = []
    if author:
        queries.append(f"{title} {author} novel")
        queries.append(f"{title} {author} book")
    queries.append(f"{title} novel")
    queries.append(f"{title} book")
    queries.append(title)

    for query in queries:
        page_title = await search_wikipedia(query, lang)
        if page_title:
            bio = await fetch_wikipedia_page(page_title, lang)
            if bio and bio.get("bio"):
                return {
                    "summary": bio.get("bio"),
                    "full_extract": bio.get("bio"),
                    "wikipedia_url": bio.get("url"),
                    "wikipedia_title": bio.get("title"),
                    "wikipedia_lang": lang,
                    "image_url": bio.get("image_url"),
                }
    return None


# ==================== GOOGLE BOOKS (FIXED) ====================

def _build_google_url(query: str, max_results: int, start_index: int = 0,
                      lang_restrict: Optional[str] = None) -> str:
    params = [
        f"q={quote_plus(query)}",
        f"maxResults={max(1, min(max_results, 40))}",
        f"startIndex={start_index}",
    ]
    if lang_restrict:
        params.append(f"langRestrict={quote_plus(lang_restrict)}")
    if settings.GOOGLE_BOOKS_API_KEY:
        params.append(f"key={quote_plus(settings.GOOGLE_BOOKS_API_KEY)}")
    return f"{GOOGLE_BOOKS_API}?{'&'.join(params)}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_json(url: str) -> Dict[str, Any]:
    req = Request(url, headers={"User-Agent": "bookie-v4/1.0"})
    try:
        with urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 429:
            logger.warning("Rate limited by external API")
            return {"items": []}
        elif e.code == 403:
            logger.warning("Access denied by external API (check API key)")
            return {"items": []}
        elif e.code == 400:
            logger.warning("Bad request to external API")
            return {"items": []}
        raise
    except URLError as e:
        logger.warning("Network error: %s", e)
        raise


async def fetch_google_books(query: str, max_results: int = 15, start_index: int = 0,
                              lang_restrict: Optional[str] = None) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    url = _build_google_url(query, max_results, start_index, lang_restrict)
    try:
        payload = await asyncio.to_thread(_fetch_json, url)
        items = payload.get("items") or []
        for item in items:
            item["_source"] = f"google_books_{lang_restrict or 'any'}"
        return items
    except Exception as e:
        logger.warning("Google Books fetch failed (%s): %s", lang_restrict or "any", e)
        return []


async def fetch_arabic_books(query: str, max_results: int = 15, start_index: int = 0) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    normalized = _normalize_arabic(query)
    return await fetch_google_books(normalized, max_results, start_index, lang_restrict="ar")


async def fetch_english_books(query: str, max_results: int = 15, start_index: int = 0) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    return await fetch_google_books(query, max_results, start_index, lang_restrict="en")


# ==================== OPENLIBRARY (FIXED) ====================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_openlibrary_books_by_author(author_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    author_name = (author_name or "").strip()
    if not author_name:
        return []
    safe_limit = max(1, min(limit, 100))
    url = f"https://openlibrary.org/search.json?author={quote_plus(author_name)}&limit={safe_limit}"
    try:
        payload = await asyncio.to_thread(_fetch_json, url)
    except Exception as e:
        logger.warning("OpenLibrary author fetch failed: %s", e)
        return []
    return _parse_openlibrary_docs(payload.get("docs", []), "openlibrary_author")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_openlibrary_books_by_title(title: str, limit: int = 20) -> List[Dict[str, Any]]:
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
        logger.warning("OpenLibrary title fetch failed: %s", e)
        return []
    return _parse_openlibrary_docs(payload.get("docs", []), "openlibrary_title")


async def fetch_openlibrary_author_works(author_name: str, limit: int = 30) -> List[Dict[str, Any]]:
    return await fetch_openlibrary_books_by_author(author_name, limit=limit)


def _parse_openlibrary_docs(docs: List[Dict], source_tag: str) -> List[Dict[str, Any]]:
    items = []
    for doc in docs:
        title = (doc.get("title") or "").strip()
        authors = list(dict.fromkeys([a for a in (doc.get("author_name") or []) if isinstance(a, str) and a.strip()]))
        if not title or not authors:
            continue

        language = None
        languages = doc.get("language") or []
        if isinstance(languages, list) and languages:
            language = languages[0]

        year = doc.get("first_publish_year")
        published_date = str(year) if year else None

        # Extract ISBNs
        isbns = doc.get("isbn") or []
        isbn_10 = None
        isbn_13 = None
        for isbn in isbns:
            if isinstance(isbn, str):
                clean = isbn.replace("-", "").replace(" ", "")
                if len(clean) == 10:
                    isbn_10 = clean
                elif len(clean) == 13:
                    isbn_13 = clean

        # Build cover URL
        cover_id = doc.get("cover_i")
        thumbnail = None
        if cover_id:
            thumbnail = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"

        items.append({
            "id": doc.get("key") or doc.get("cover_edition_key") or title,
            "_source": source_tag,
            "volumeInfo": {
                "title": title,
                "authors": authors,
                "publishedDate": published_date,
                "language": language,
                "categories": doc.get("subject", [])[:10],
                "description": doc.get("first_sentence", {}).get("value") if isinstance(doc.get("first_sentence"), dict) else doc.get("first_sentence"),
                "industryIdentifiers": [
                    {"type": "ISBN_10", "identifier": isbn_10} if isbn_10 else None,
                    {"type": "ISBN_13", "identifier": isbn_13} if isbn_13 else None,
                ],
                "imageLinks": {"thumbnail": thumbnail} if thumbnail else {},
                "pageCount": doc.get("number_of_pages_median"),
                "publisher": (doc.get("publisher") or [None])[0],
            },
        })
    return items