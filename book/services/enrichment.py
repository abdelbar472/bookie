"""
Enrichment Service V4 - Rich Descriptions for Book, Author & Series
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict

from models.book import BookProfile, ContentAnalysis, QualityMetrics
from models.author import AuthorProfile, AuthorBio, AuthorStyleProfile, AuthorStats
from models.series import SeriesProfile, SeriesBookEntry
from clients.external import fetch_all_sources, fetch_google_books
from services.wikipedia import resolve_author, resolve_book_wikipedia
from utils.helpers import slugify, is_arabic
from database import db

logger = logging.getLogger(__name__)


class EnrichmentService:

    # ====================== BOOK ======================
    async def enrich_book(self, query: str) -> Optional[BookProfile]:
        """Enrich single book with rich description"""
        logger.info(f"Enriching book: {query}")

        raw_items = await fetch_all_sources(query, max_results=15)
        if not raw_items:
            logger.warning(f"No data found for book: {query}")
            return None

        works = self._group_editions_strong(raw_items)
        if not works:
            return None

        best = works[0]
        wiki = await resolve_book_wikipedia(best["title"], best.get("primary_author"))

        profile = self._build_rich_book_profile(best, wiki)
        await db.save_book(profile)

        logger.info(f"✅ Book enriched: {profile.title}")
        return profile

    def _group_editions_strong(self, raw_items: List[Dict]) -> List[Dict]:
        groups = {}
        for item in raw_items:
            if "volumeInfo" in item:  # Google Books
                vol = item["volumeInfo"]
                title = vol.get("title", "").strip()
                authors = vol.get("authors", ["Unknown"])
            else:  # OpenLibrary etc.
                title = item.get("title", "").strip()
                authors = item.get("author_name", ["Unknown"])
                if not isinstance(authors, list):
                    authors = [authors]

            if not title:
                continue

            primary_author = authors[0] if authors else "Unknown"
            work_id = f"{slugify(title)}-{slugify(primary_author)}"

            if work_id not in groups:
                groups[work_id] = {
                    "work_id": work_id,
                    "title": title,
                    "primary_author": primary_author,
                    "authors": authors,
                    "description": item.get("description") or vol.get("description") if 'vol' in locals() else None,
                    "first_published_year": item.get("first_publish_year") or vol.get("publishedDate") if 'vol' in locals() else None,
                    "image_url": item.get("cover_url") or vol.get("imageLinks", {}).get("thumbnail") if 'vol' in locals() else None,
                }
        return list(groups.values())

    def _build_rich_book_profile(self, work: Dict, wiki: Dict) -> BookProfile:
        # Rich description from Wikipedia or fallback
        description = (wiki.get("clean_summary") or 
                      wiki.get("summary") or 
                      work.get("description") or 
                      f"{work['title']} is a significant literary work by {work['primary_author']}.")

        return BookProfile(
            work_id=work["work_id"],
            title=work["title"],
            primary_author=work["primary_author"],
            authors=work["authors"],
            description=description,
            first_published_year=work.get("first_published_year"),
            original_language="ar" if is_arabic(work["title"]) else "en",
            image_url=work.get("image_url") or wiki.get("image_url"),
            wikipedia_url=wiki.get("wikipedia_url"),
            content_analysis=ContentAnalysis(),
            quality=QualityMetrics(source_count=3),
            rag_document=self._build_book_rag_doc(work["title"], work["primary_author"], description, wiki),
        )

    def _build_book_rag_doc(self, title: str, author: str, desc: str, wiki: Dict) -> str:
        return f"""Title: {title}
Author: {author}
Description: {desc[:950]}

Wikipedia Summary: {wiki.get('clean_summary', wiki.get('summary', ''))[:600]}
"""

    # ====================== AUTHOR ======================
    async def enrich_author(self, author_name: str) -> Optional[AuthorProfile]:
        """Enrich author with rich biography and books"""
        logger.info(f"Enriching author: {author_name}")

        wiki = await resolve_author(author_name)
        
        # Fetch author's books
        books = await self._fetch_books_by_author(author_name, limit=10)

        full_bio = wiki.get("bio") or wiki.get("full_extract") or f"{author_name} is a prominent author."
        short_bio = wiki.get("short_bio") or (full_bio[:320] + "..." if len(full_bio) > 320 else full_bio)

        # Extract notable works from books
        notable_works = [book.work_id for book in books[:10]] if books else []

        author_profile = AuthorProfile(
            author_id=slugify(author_name),
            name=author_name,
            bio=AuthorBio(
                short_bio=short_bio,
                full_bio=full_bio,
                wikipedia_url=wiki.get("wikipedia_url"),
                wikipedia_lang=wiki.get("wikipedia_lang", "en")
            ),
            image_url=wiki.get("image_url"),
            style_profile=AuthorStyleProfile(
                description=full_bio[:500] or f"{author_name} is a distinguished writer."
            ),
            stats=AuthorStats(
                total_works=len(books),
                series_count=0  # Could be calculated from books with series
            ),
            notable_works=notable_works,
            books=books,  # Include the fetched books
            rag_document=self._build_author_rag_doc(author_name, full_bio, books, wiki),
        )

        await db.save_author(author_profile)
        logger.info(f"✅ Author enriched: {author_name} | Books found: {len(books)}")
        return author_profile

    def _build_author_rag_doc(self, name: str, bio: str, books: List[BookProfile], wiki: Dict) -> str:
        book_list = "\n".join([f"• {book.title}" for book in books[:10]])
        return f"""Author: {name}

Biography:
{bio[:1500]}

Source: Wikipedia ({wiki.get('wikipedia_lang', 'en')})

Books:
{book_list}
"""

    async def _fetch_books_by_author(self, author_name: str, limit: int = 50) -> List[BookProfile]:
        """Fetch books by author using Google Books API"""
        logger.info(f"Fetching books for author: {author_name}")
        # Google Books API has a limit of 10 results without an API key
        max_results = min(limit, 10)
        items = await fetch_google_books(f"inauthor:{author_name}", max_results=max_results)
        logger.info(f"Google Books API returned {len(items)} items for author: {author_name}")
        books = []
        
        for item in items:
            volume = item.get("volumeInfo", {})
            title = volume.get("title", "").strip()
            if not title:
                continue

            # Convert published date to int or None
            published_date = volume.get("publishedDate", "")
            try:
                first_published_year = int(published_date.split("-")[0]) if published_date else None
            except (ValueError, IndexError):
                first_published_year = None

            book = BookProfile(
                work_id=f"{slugify(title)}-{slugify(author_name)}",
                title=title,
                primary_author=author_name,
                authors=volume.get("authors", [author_name]),
                description=volume.get("description", ""),
                first_published_year=first_published_year,
                image_url=volume.get("imageLinks", {}).get("thumbnail", ""),
            )
            books.append(book)
        
        logger.info(f"Created {len(books)} BookProfile objects for author: {author_name}")
        return books[:limit]

    # ====================== SERIES ======================
    async def enrich_series(self, series_name: str) -> Optional[SeriesProfile]:
        """Enrich Series with rich description"""
        logger.info(f"Enriching series: {series_name}")

        raw_items = await fetch_all_sources(series_name, max_results=15)
        if not raw_items:
            return None

        books = []
        primary_author = "Unknown"

        for item in raw_items[:12]:
            if "volumeInfo" in item:
                vol = item["volumeInfo"]
                title = vol.get("title")
                author = vol.get("authors", ["Unknown"])[0] if vol.get("authors") else "Unknown"
            else:
                title = item.get("title")
                author = item.get("author_name")
                if isinstance(author, list):
                    author = author[0] if author else "Unknown"
                else:
                    author = author or "Unknown"

            if title:
                work_id = f"{slugify(title)}-{slugify(author)}"
                books.append(SeriesBookEntry(
                    work_id=work_id,
                    title=title,
                    position=len(books) + 1,
                    published_year=item.get("first_publish_year")
                ))
                if primary_author == "Unknown":
                    primary_author = author

        if not books:
            return None

        wiki = await resolve_book_wikipedia(series_name, primary_author)

        series_profile = SeriesProfile(
            series_id=f"{slugify(series_name)}-{slugify(primary_author)}",
            series_name=series_name,
            primary_author=primary_author,
            author_id=slugify(primary_author),
            description=wiki.get("summary") or f"The {series_name} series.",
            premise=wiki.get("full_extract"),
            books=books,
            total_books=len(books),
            rag_document=self._build_series_rag_doc(series_name, books, primary_author, wiki),
        )

        await db.save_series(series_profile)
        return series_profile

    def _build_series_rag_doc(self, name: str, books: List[SeriesBookEntry], author: str, wiki: Dict) -> str:
        book_list = "\n".join([f"• {b.title}" for b in books[:10]])
        return f"""Series: {name}
By: {author}
Total Books: {len(books)}

Description:
{wiki.get('summary', 'A remarkable book series.')}

Books in Series:
{book_list}
"""


# Global Instance
enrichment_service = EnrichmentService()