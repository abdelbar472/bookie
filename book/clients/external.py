"""
External Clients - Using multiple free sources in parallel
"""

import asyncio
import logging
from typing import List, Dict, Optional
import aiohttp

from utils.helpers import is_arabic
from config import settings

logger = logging.getLogger(__name__)


async def fetch_all_sources(query: str, max_results: int = 15) -> List[Dict]:
    """Fetch from all sources in parallel"""
    tasks = [
        fetch_openlibrary(query, max_results),
        fetch_google_books(query, max_results),
        fetch_internet_archive(query, max_results // 2),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)

    logger.info(f"Fetched {len(all_items)} raw items for query: {query}")
    return all_items


async def fetch_openlibrary(query: str, limit: int = 15) -> List[Dict]:
    url = "https://openlibrary.org/search.json"
    params = {"q": query, "limit": limit}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("docs", [])
        except Exception as e:
            logger.warning(f"OpenLibrary error: {e}")
    return []


async def fetch_google_books(query: str, max_results: int = 15) -> List[Dict]:
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": query,
        "maxResults": max_results,
        "printType": "books"
    }
    if settings.GOOGLE_BOOKS_API_KEY:
        params["key"] = settings.GOOGLE_BOOKS_API_KEY

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("items", [])
        except Exception as e:
            logger.warning(f"Google Books error: {e}")
            return []
    return []

async def fetch_internet_archive(query: str, limit: int = 8) -> List[Dict]:
    url = "https://archive.org/advancedsearch.php"
    params = {
        "q": query,
        "fl[]": "identifier,title,creator,description,year",
        "rows": limit,
        "output": "json"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", {}).get("docs", [])
        except Exception:
            return []
    return []


async def fetch_author_books(author_name: str) -> List[Dict]:
    """Fetch author's books from OpenLibrary"""
    url = "https://openlibrary.org/search.json"
    params = {"author": author_name, "limit": 50}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    docs = data.get("docs", [])
                    books = [{"title": doc.get("title", ""), "year": doc.get("first_publish_year")} for doc in docs if doc.get("title")]
                    return books
        except Exception as e:
            logger.warning(f"OpenLibrary author books error: {e}")
    return []


# Wikipedia functions will go in services/wikipedia.py
async def resolve_author(author_name: str):
    # Will be implemented in next files
    pass


__all__ = ["fetch_all_sources", "fetch_openlibrary", "fetch_google_books", "fetch_internet_archive", "fetch_author_books"]
