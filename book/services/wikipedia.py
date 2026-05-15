# services/wikipedia.py
import asyncio
import re
import logging
from typing import Dict, Optional
import aiohttp

from utils.helpers import is_arabic
from config import settings

logger = logging.getLogger(__name__)


async def resolve_author(author_name: str) -> Dict:
    """Improved Wikipedia Author Fetch"""
    if not author_name:
        return _fallback("author")

    languages = ["ar", "en"] if is_arabic(author_name) else ["en", "ar"]
    variants = [author_name.strip(), author_name.replace(" ", "_")]

    async with aiohttp.ClientSession() as session:
        for lang in languages:
            for variant in variants:
                try:
                    data = await _fetch_wikipedia_page(session, variant, lang, is_author=True)
                    if data.get("bio") and len(data["bio"]) > 150:
                        return data
                except Exception:
                    continue
    return _fallback("author", author_name)


async def resolve_book_wikipedia(title: str, author: Optional[str] = None) -> Dict:
    """Improved Wikipedia Book Fetch"""
    search = f"{title} {author}" if author else title
    languages = ["ar", "en"] if is_arabic(title) else ["en", "ar"]

    async with aiohttp.ClientSession() as session:
        for lang in languages:
            try:
                data = await _fetch_wikipedia_page(session, search, lang, is_author=False)
                if data.get("summary") and len(data["summary"]) > 100:
                    return data
            except Exception:
                continue
    return {}


async def resolve_series_wikipedia(series_name: str) -> Dict:
    """
    Find SERIES pages on Wikipedia (not individual book pages)
    Returns series metadata including book list if available
    """
    if not series_name:
        return {"books_in_order": []}
    
    # Try multiple variants to find series page
    variants = [
        series_name,
        f"{series_name} series",
        f"{series_name} (series)",
        f"{series_name} (novel series)",
        f"{series_name} (book series)",
        f"{series_name} (franchise)",
    ]
    
    languages = ["ar", "en"] if is_arabic(series_name) else ["en", "ar"]
    
    async with aiohttp.ClientSession() as session:
        for lang in languages:
            for variant in variants:
                try:
                    data = await _fetch_series_page(session, variant, lang)
                    if data.get("books_in_order") and len(data["books_in_order"]) > 1:
                        logger.info(f"✅ Found series page for '{series_name}': {len(data['books_in_order'])} books")
                        return data
                except Exception as e:
                    logger.debug(f"Series variant '{variant}' ({lang}): {e}")
                    continue
    
    logger.warning(f"⚠️ No series page found for: {series_name}")
    return {"books_in_order": []}


async def _fetch_series_page(session, title: str, lang: str) -> Dict:
    """
    Fetch series page and extract book list
    Wikipedia series pages often have sections like 'Books in series' or tables
    """
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "extracts|pageimages",
        "explaintext": True,
        "exintro": False,  # Get full extract, not just intro
        "piprop": "thumbnail",
        "pithumbsize": 600,
    }
    
    async with session.get(url, params=params, timeout=12) as resp:
        data = await resp.json()
    
    page = next(iter(data.get("query", {}).get("pages", {}).values()), {})
    if page.get("missing"):
        return {}
    
    extract = page.get("extract", "")
    if not extract or len(extract) < 200:
        return {}
    
    # Try to extract book list from the extract
    books = _parse_series_books_from_text(extract)
    
    return {
        "books_in_order": books,
        "summary": extract[:500],
        "wikipedia_url": page.get("fullurl"),
        "wikipedia_title": page.get("title"),
        "image_url": page.get("thumbnail", {}).get("source"),
    }


def _parse_series_books_from_text(text: str) -> list:
    """
    Extract book titles and order from Wikipedia series page text
    Looks for patterns like:
    - "Book 1: Title"
    - "1. Title"
    - Numbered lists in 'Books in series' sections
    """
    books = []
    lines = text.split("\n")
    
    in_series_section = False
    book_order = 0
    
    for line in lines:
        line = line.strip()
        
        # Detect series section headers
        if any(header in line.lower() for header in ["books in", "novels in", "main series", "published books"]):
            in_series_section = True
            continue
        
        # Stop if we hit another major section
        if in_series_section and any(skip in line.lower() for skip in ["related", "adaptation", "reception", "==", "references"]):
            in_series_section = False
            continue
        
        if not in_series_section:
            continue
        
        # Pattern: "1. Title (year)" or "Book 1: Title"
        match = re.match(r'^(?:Book\s+)?(\d+)[\.\):\s]+(.+?)(?:\s*\(.*\d{4}.*\))?$', line)
        if match:
            order = int(match.group(1))
            title = match.group(2).strip()
            books.append({"title": title, "order": order})
            book_order = order + 1
            continue
        
        # Fallback: just number followed by title
        if re.match(r'^\d+\s+[A-Z]', line) and len(line) > 10:
            parts = re.split(r'\s+', line, 1)
            if len(parts) == 2 and parts[1]:
                books.append({"title": parts[1], "order": book_order})
                book_order += 1
    
    return books


async def _fetch_wikipedia_page(session, title: str, lang: str, is_author: bool) -> Dict:
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "extracts|pageimages|info",
        "exintro": False,  # Get full extract for authors, not just intro
        "explaintext": True,
        "exsentences": 25 if is_author else 12,  # More sentences for authors
        "piprop": "thumbnail",
        "pithumbsize": 600,
        "inprop": "url"
    }

    async with session.get(url, params=params, timeout=12) as resp:
        data = await resp.json()

    page = next(iter(data.get("query", {}).get("pages", {}).values()), {})
    if page.get("missing"):
        return {}

    extract = re.sub(r'\[\d+\]', '', page.get("extract", "")).strip()
    extract = re.sub(r'\s+', ' ', extract).strip()

    return {
        "bio": extract if is_author else None,
        "summary": extract if not is_author else None,
        "full_extract": extract,
        "wikipedia_url": page.get("fullurl"),
        "wikipedia_title": page.get("title"),
        "wikipedia_lang": lang,
        "image_url": page.get("thumbnail", {}).get("source"),
        "clean_summary": extract[:800] if extract else None
    }


def _fallback(type_: str, name: str = "") -> Dict:
    return {
        "bio": None,
        "short_bio": f"{name} is a {type_}." if name else f"Unknown {type_}",
        "wikipedia_url": None,
        "image_url": None,
    }

