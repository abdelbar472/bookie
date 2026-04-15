"""
V3 Enrichment Engine: Transforms raw API data into rich RAG-ready profiles
"""
import re
import logging
from typing import List, Dict, Optional, Any, Set
from datetime import datetime, timezone
from collections import Counter

from .schemas import (
    BookProfile, AuthorProfile, SeriesProfile,
    ContentAnalysis, QualityMetrics, EditionEnriched,
    AuthorBio, AuthorStyleProfile, AuthorStats,
    SeriesBookEntry, ThemeCategory, ContentTone
)
from .external_clients import (
    fetch_google_books, fetch_arabic_books, fetch_english_books,
    fetch_openlibrary_books_by_author, fetch_openlibrary_books_by_title,
    resolve_author, _slugify, _is_arabic, _normalize_arabic
)

logger = logging.getLogger(__name__)


class EnrichmentEngine:
    """
    Transforms raw book data into enriched profiles for RAG
    """

    def __init__(self):
        self.theme_keywords = {
            ThemeCategory.IDENTITY: ["identity", "self-discovery", "who am i", "finding oneself", "self"],
            ThemeCategory.POWER: ["power", "control", "corruption", "authority", "domination", "politics"],
            ThemeCategory.LOVE: ["love", "romance", "relationship", "heart", "passion", "marriage"],
            ThemeCategory.WAR: ["war", "battle", "conflict", "soldier", "military", "fight", "combat"],
            ThemeCategory.TECHNOLOGY: ["technology", "ai", "robot", "computer", "future", "science", "cyber"],
            ThemeCategory.NATURE: ["nature", "environment", "wilderness", "survival", "earth", "ecology"],
            ThemeCategory.SOCIETY: ["society", "class", "social", "culture", "community", "civilization"],
            ThemeCategory.COMING_OF_AGE: ["growing up", "coming of age", "adolescence", "maturity", "youth"],
            ThemeCategory.GOOD_VS_EVIL: ["good vs evil", "morality", "darkness", "light", "hero", "villain"],
            ThemeCategory.SURVIVAL: ["survival", "survive", "danger", "threat", "alive", "perseverance"],
            ThemeCategory.BETRAYAL: ["betrayal", "treason", "deception", "lies", "trust"],
            ThemeCategory.REDEMPTION: ["redemption", "forgiveness", "salvation", "atonement"],
            ThemeCategory.FRIENDSHIP: ["friendship", "friends", "loyalty", "companions"],
            ThemeCategory.FAMILY: ["family", "parents", "children", "legacy", "inheritance", "kin", "brother", "sister"],
            "mystery": ["mystery", "investigation", "detective", "murder", "clue", "suspense"],
            "magic": ["magic", "wizard", "witch", "spell", "sorcery", "fantasy", "enchantment"],
            "historical": ["history", "past", "century", "ancient", "historical"],
        }

        self.tone_indicators = {
            ContentTone.DARK: ["dark", "grim", "shadow", "death", "blood", "gothic", "noir", "bleak", "macabre"],
            ContentTone.LIGHT: ["light", "humor", "funny", "comedy", "wit", "cheerful", "whimsical", "warm"],
            ContentTone.HUMOROUS: ["humor", "funny", "comedy", "wit", "satire", "parody", "hilarious"],
            ContentTone.PHILOSOPHICAL: ["philosophy", "meaning", "existence", "think", "meditation", "contemplative"],
            ContentTone.ACTION_PACKED: ["action", "fight", "battle", "chase", "war", "adventure", "thrilling", "fast-paced"],
            ContentTone.ROMANTIC: ["love", "romance", "heart", "passion", "intimacy", "relationship"],
            ContentTone.MYSTERIOUS: ["mystery", "secret", "unknown", "suspense", "enigma", "detective", "puzzle"],
            ContentTone.MELANCHOLIC: ["sad", "melancholy", "loss", "grief", "nostalgia", "longing", "sorrow"],
            ContentTone.HOPEFUL: ["hope", "uplifting", "inspiring", "triumph", "victory", "dream", "optimistic"],
        }

    # ==================== MAIN ENTRY POINTS ====================

    async def enrich_books_from_query(self, query: str, include_arabic: bool = False) -> List[BookProfile]:
        """
        Main entry: Fetch and enrich books from search query
        """
        logger.info(f"Enriching books for query: {query}")

        # Fetch from multiple sources
        raw_items = await self._fetch_all_sources(query, include_arabic)

        if not raw_items:
            logger.warning(f"No results found for query: {query}")
            return []

        # Group and deduplicate
        grouped = self._group_editions(raw_items)
        logger.info(f"Grouped into {len(grouped)} unique works")

        # Enrich each work
        profiles = []
        for work_data in grouped:
            try:
                profile = await self._create_book_profile(work_data)
                profiles.append(profile)
            except Exception as e:
                logger.error(f"Failed to enrich work {work_data.get('title')}: {e}")
                continue

        return profiles

    async def enrich_author(self, author_name: str, books: List[BookProfile]) -> AuthorProfile:
        """
        Create enriched author profile from books + Wikipedia
        """
        logger.info(f"Enriching author: {author_name}")

        # Fetch Wikipedia data
        wiki_data = await resolve_author(author_name)

        # Build bio
        bio = AuthorBio(
            short_bio=self._truncate_text(wiki_data.get("bio"), 300) if wiki_data.get("bio") else None,
            full_bio=wiki_data.get("bio"),
            wikipedia_url=wiki_data.get("wikipedia_url"),
            wikipedia_title=wiki_data.get("wikipedia_title"),
            wikipedia_lang=wiki_data.get("wikipedia_lang", "en"),
        )

        # Analyze style from books
        style = self._analyze_author_style(books, author_name)

        # Compute stats
        stats = self._compute_author_stats(books)

        # Build profile
        profile = AuthorProfile(
            author_id=_slugify(author_name),
            name=author_name,
            name_variants=wiki_data.get("aliases", []),
            image_url=wiki_data.get("image_url"),
            bio=bio,
            style_profile=style,
            notable_works=[b.work_id for b in books[:10]],
            series=list(set(b.series_name for b in books if b.series_name)),
            stats=stats,
            rag_document=self._build_author_rag_doc(author_name, bio, style, books),
        )

        return profile

    async def enrich_series(self, series_name: str, books: List[BookProfile]) -> SeriesProfile:
        """
        Create enriched series profile from constituent books
        """
        logger.info(f"Enriching series: {series_name}")

        if not books:
            return SeriesProfile(
                series_id=_slugify(series_name),
                series_name=series_name,
                primary_author="Unknown",
                author_id="unknown"
            )

        # Sort by position
        sorted_books = sorted(books, key=lambda b: (b.series_position or 999, b.first_published_year or 9999))

        # Build entries
        entries = []
        for i, book in enumerate(sorted_books, 1):
            entry = SeriesBookEntry(
                work_id=book.work_id,
                title=book.title,
                position=book.series_position or float(i),
                published_year=book.first_published_year,
                is_core=True,
                summary=self._truncate_text(book.description, 200) if book.description else None,
            )
            entries.append(entry)

        # Analyze themes
        all_themes = []
        for book in books:
            all_themes.extend(book.content_analysis.key_themes)
        main_themes = [t for t, _ in Counter(all_themes).most_common(7)]

        primary_author = books[0].primary_author

        profile = SeriesProfile(
            series_id=f"{_slugify(series_name)}-{_slugify(primary_author)}",
            series_name=series_name,
            primary_author=primary_author,
            author_id=_slugify(primary_author),
            description=f"The {series_name} series by {primary_author}.",
            premise=self._extract_series_premise(books),
            books=entries,
            total_books=len(books),
            main_themes=main_themes,
            reading_order=[e.work_id for e in entries],
            rag_document=self._build_series_rag_doc(series_name, entries, main_themes, primary_author),
        )

        return profile

    # ==================== BOOK ENRICHMENT ====================

    async def _create_book_profile(self, work_data: Dict) -> BookProfile:
        """Create BookProfile from grouped work data"""

        work_id = work_data["work_id"]
        title = work_data["title"]
        authors = work_data["authors"]
        primary_author = work_data["primary_author"]

        # Build enriched editions
        editions = []
        for ed in work_data.get("editions", []):
            edition = EditionEnriched(
                edition_id=ed.get("book_id", "unknown"),
                isbn_10=self._extract_isbn(ed, "ISBN_10"),
                isbn_13=self._extract_isbn(ed, "ISBN_13"),
                published_date=ed.get("published_date"),
                publisher=ed.get("publisher"),
                page_count=ed.get("page_count"),
                language=ed.get("language"),
                format=ed.get("format"),
                thumbnail=ed.get("thumbnail"),
                data_sources=[ed.get("source", "unknown")],
            )
            editions.append(edition)

        # Content analysis
        description = work_data.get("description", "") or ""
        content_analysis = self._analyze_content(description, title)

        # Quality metrics
        quality = self._calculate_quality(work_data, editions)

        # Extract metadata
        first_year = self._extract_year(work_data.get("published_date"))

        # Build profile
        profile = BookProfile(
            work_id=work_id,
            google_books_id=work_data.get("google_books_id"),
            openlibrary_key=work_data.get("openlibrary_key"),
            title=title,
            subtitle=work_data.get("subtitle"),
            authors=authors,
            primary_author=primary_author,
            series_name=work_data.get("saga_name"),
            series_position=work_data.get("series_position"),
            description=description if description else None,
            description_sources=["google_books"],  # Could be multiple
            content_analysis=content_analysis,
            categories=work_data.get("categories", []),
            genres=self._extract_genres(work_data.get("categories", [])),
            keywords=self._extract_keywords(title, description),
            editions=editions,
            edition_count=len(editions),
            quality=quality,
            first_published_year=first_year,
            original_language=editions[0].language if editions else "en",
            rag_document=self._build_book_rag_doc(title, authors, description, content_analysis,
                                                  work_data.get("categories", [])),
        )

        return profile

    def _analyze_content(self, description: str, title: str) -> ContentAnalysis:
        """Analyze book content for themes, tone, entities"""
        text = f"{title} {description}".lower()

        # Theme detection
        detected_themes = []
        dominant_categories = []
        for theme, keywords in self.theme_keywords.items():
            matches = [kw for kw in keywords if kw in text]
            if matches:
                detected_themes.extend(matches[:2])
                dominant_categories.append(theme)

        # Tone detection
        detected_tones = []
        for tone, indicators in self.tone_indicators.items():
            if any(ind in text for ind in indicators):
                detected_tones.append(tone)

        if not detected_tones:
            detected_tones = [ContentTone.SERIOUS]

        # Mood detection
        mood = self._detect_mood(text)

        # Entity extraction (simplified)
        characters = self._extract_entities(description, "character")
        locations = self._extract_entities(description, "location")

        # Target audience
        target_audience = self._detect_audience(text)

        return ContentAnalysis(
            key_themes=list(set(detected_themes))[:8],
            dominant_themes=list(set(dominant_categories))[:4],
            tone=detected_tones,
            mood=mood,
            pacing=self._detect_pacing(text),
            characters=characters[:10],
            locations=locations[:5],
            target_audience=target_audience,
        )

    def _calculate_quality(self, work_data: Dict, editions: List[EditionEnriched]) -> QualityMetrics:
        """Calculate data quality score"""
        desc = work_data.get("description", "") or ""
        desc_quality = min(100, len(desc) / 20) if desc else 0  # 2000 chars = 100

        sources = set()
        for ed in editions:
            sources.update(ed.data_sources)

        return QualityMetrics(
            description_quality=int(desc_quality),
            has_cover=any(ed.thumbnail for ed in editions),
            has_isbn=any(ed.isbn_13 or ed.isbn_10 for ed in editions),
            has_page_count=any(ed.page_count for ed in editions),
            has_publisher=any(ed.publisher for ed in editions),
            has_language=any(ed.language for ed in editions),
            source_count=len(sources),
            confidence_score=min(1.0, len(sources) * 0.3 + (desc_quality / 200)),
        )

    # ==================== FETCHING & GROUPING ====================

    async def _fetch_all_sources(self, query: str, include_arabic: bool) -> List[Dict]:
        """Fetch from all available sources"""
        all_items = []

        # Google Books (general)
        items = await fetch_google_books(query, max_results=20)
        all_items.extend(items)

        # Language-specific
        if include_arabic or _is_arabic(query):
            arabic_items = await fetch_arabic_books(query, max_results=15)
            all_items.extend(arabic_items)

        # Always try OpenLibrary for better descriptions/coverage as fallback
        if len(all_items) < 30:
            ol_items = await fetch_openlibrary_books_by_title(query, limit=10)
            all_items.extend(ol_items)

        return all_items

    def _group_editions(self, raw_items: List[Dict]) -> List[Dict]:
        """
        Group different editions of the same work together
        Similar to V2 normalize_and_group but enhanced
        """
        groups: Dict[str, Dict] = {}

        for item in raw_items:
            volume = item.get("volumeInfo", {})
            authors = volume.get("authors", [])
            if not authors:
                continue

            primary_author = authors[0]
            title = volume.get("title", "Unknown").strip()
            work_id = self._create_work_id(title, primary_author)

            # Series detection
            series_info = self._extract_series_info(title)

            # Build edition
            edition = {
                "book_id": item.get("id") or self._extract_isbn_from_volume(volume),
                "published_date": volume.get("publishedDate"),
                "thumbnail": volume.get("imageLinks", {}).get("thumbnail"),
                "language": volume.get("language"),
                "categories": volume.get("categories", []),
                "publisher": volume.get("publisher"),
                "page_count": volume.get("pageCount"),
                "format": self._detect_format(volume),
                "source": item.get("_source", "google_books"),
            }

            if work_id not in groups:
                groups[work_id] = {
                    "work_id": work_id,
                    "title": title,
                    "subtitle": volume.get("subtitle"),
                    "authors": authors,
                    "primary_author": primary_author,
                    "description": volume.get("description"),
                    "categories": volume.get("categories", []),
                    "saga_name": series_info.get("name"),
                    "series_position": series_info.get("position"),
                    "editions": [],
                    "google_books_id": item.get("id") if "google" in item.get("_source", "") else None,
                    "openlibrary_key": item.get("id") if "openlibrary" in item.get("_source", "") else None,
                }
            else:
                # Merge better description
                new_desc = volume.get("description")
                if new_desc and len(new_desc) > len(groups[work_id].get("description") or ""):
                    groups[work_id]["description"] = new_desc

                # Merge categories
                new_cats = volume.get("categories", [])
                if new_cats:
                    ext_cats = set(groups[work_id].get("categories", []))
                    ext_cats.update(new_cats)
                    groups[work_id]["categories"] = list(ext_cats)

            groups[work_id]["editions"].append(edition)

        return list(groups.values())

    # ==================== UTILITY METHODS ====================

    def _create_work_id(self, title: str, primary_author: str) -> str:
        """Create canonical work ID"""
        t = _normalize_arabic(title) if _is_arabic(title) else title
        t = re.sub(r"[^\w\s-]", "", t.lower().strip())
        t = re.sub(r"[\s-]+", "-", t)
        a = _slugify(primary_author)
        return f"{t}-{a}"[:120]

    def _extract_series_info(self, title: str) -> Dict[str, Any]:
        """Extract series name and position from title"""
        # Pattern: "Title (Series Name, #1)" or "Title (Series Name #1)"
        match = re.search(r'\(([^)]+)(?:,?\s*#?([0-9]+(?:\.\d+)?))\s*\)', title, re.IGNORECASE)
        if match:
            return {
                "name": match.group(1).strip(),
                "position": float(match.group(2)) if match.group(2) else None
            }

        # Pattern: "Title - Series Name, Book X" or similar
        match = re.search(r'(?:-|—)\s*(.+?)(?:\s+(?:book|vol\.?|volume|part)\s+(\d+))', title, re.IGNORECASE)
        if match:
            return {"name": match.group(1).strip(), "position": float(match.group(2))}

        # Pattern: "Series Name: Book Title"
        if ':' in title:
            parts = title.split(':', 1)
            potential_series = parts[0].strip()
            # Heuristic: if series part is short and doesn't look like a subtitle
            if len(potential_series.split()) <= 4 and not potential_series.endswith('?'):
                return {"name": potential_series, "position": None}

        return {}

    def _extract_isbn(self, edition: Dict, type_: str) -> Optional[str]:
        """Extract ISBN from edition data"""
        identifiers = edition.get("industryIdentifiers", [])
        for ident in identifiers:
            if ident.get("type") == type_:
                return ident.get("identifier")
        return None

    def _extract_isbn_from_volume(self, volume: Dict) -> str:
        """Extract ISBN from volume info"""
        ids = volume.get("industryIdentifiers", [])
        for ident in ids:
            if ident.get("type") in ["ISBN_13", "ISBN_10"]:
                return ident.get("identifier")
        return volume.get("title", "unknown")

    def _extract_year(self, date_str: Optional[str]) -> Optional[int]:
        """Extract year from date string"""
        if not date_str:
            return None
        match = re.search(r'\d{4}', date_str)
        return int(match.group()) if match else None

    def _detect_format(self, volume: Dict) -> Optional[str]:
        """Detect book format from metadata"""
        title = volume.get("title", "").lower()
        if "audiobook" in title or "audio" in title:
            return "audiobook"
        if "ebook" in title or "kindle" in title:
            return "ebook"
        # Could use page count heuristics
        pages = volume.get("pageCount")
        if pages:
            if pages < 50:
                return "short_story"
            elif pages > 500:
                return "hardcover"
        return "paperback"

    def _extract_genres(self, categories: List[str]) -> List[str]:
        """Extract standard genres from categories"""
        genre_map = {
            "fiction": "Fiction",
            "non-fiction": "Non-Fiction",
            "nonfiction": "Non-Fiction",
            "science fiction": "Science Fiction",
            "sci-fi": "Science Fiction",
            "fantasy": "Fantasy",
            "mystery": "Mystery",
            "thriller": "Thriller",
            "horror": "Horror",
            "romance": "Romance",
            "biography": "Biography",
            "history": "History",
            "young adult": "Young Adult",
            "children": "Children's",
        }

        genres = []
        for cat in categories:
            cat_lower = cat.lower()
            for key, val in genre_map.items():
                if key in cat_lower and val not in genres:
                    genres.append(val)

        return genres or ["Literature"]

    def _extract_keywords(self, title: str, description: Optional[str]) -> List[str]:
        """Extract search keywords"""
        text = f"{title} {description or ''}".lower()
        words = re.findall(r'\b[a-z]{5,}\b', text)
        # Filter common stop words
        stop_words = {"about", "after", "again", "against", "could", "would", "should"}
        filtered = [w for w in words if w not in stop_words]
        return [w for w, _ in Counter(filtered).most_common(15)]

    def _extract_entities(self, text: Optional[str], entity_type: str) -> List[str]:
        """Simple entity extraction (placeholder for NER)"""
        if not text:
            return []
        # This is a simplified version - in production, use spaCy or similar
        return []

    def _detect_mood(self, text: str) -> str:
        """Detect overall mood"""
        if any(w in text for w in ["dark", "grim", "bleak", "hopeless", "despair"]):
            return "dark"
        if any(w in text for w in ["hopeful", "uplifting", "inspiring", "triumph"]):
            return "hopeful"
        if any(w in text for w in ["tense", "suspense", "thrilling", "anxiety"]):
            return "tense"
        if any(w in text for w in ["peaceful", "calm", "serene", "quiet"]):
            return "peaceful"
        return "neutral"

    def _detect_pacing(self, text: str) -> str:
        """Detect narrative pacing"""
        if any(w in text for w in ["fast-paced", "relentless", "gripping", "page-turner"]):
            return "fast"
        if any(w in text for w in ["slow", "meandering", "contemplative", "leisurely"]):
            return "slow"
        return "moderate"

    def _detect_audience(self, text: str) -> Optional[str]:
        """Detect target audience"""
        if any(w in text for w in ["young adult", "ya ", "teenager", "coming of age"]):
            return "Young Adult"
        if any(w in text for w in ["children", "kids", "middle grade", "ages 8"]):
            return "Children"
        if any(w in text for w in ["adult", "mature", "graphic", "explicit"]):
            return "Adult"
        return None

    def _truncate_text(self, text: Optional[str], max_len: int) -> Optional[str]:
        """Truncate text with ellipsis"""
        if not text:
            return None
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    # ==================== AUTHOR HELPERS ====================

    def _analyze_author_style(self, books: List[BookProfile], author_name: str) -> AuthorStyleProfile:
        """Analyze writing style from books"""
        all_themes = []
        all_genres = []
        all_tones = []

        for book in books:
            all_themes.extend(book.content_analysis.key_themes)
            all_genres.extend(book.genres)
            all_tones.extend(book.content_analysis.tone)

        top_genres = [g for g, _ in Counter(all_genres).most_common(5)]
        top_themes = [t for t, _ in Counter(all_themes).most_common(6)]

        return AuthorStyleProfile(
            description=f"{author_name} writes primarily {', '.join(top_genres[:2])} "
                        f"exploring themes of {', '.join(top_themes[:3])}.",
            genres=top_genres,
            common_themes=top_themes,
            tone=list(set(all_tones))[:4],
        )

    def _compute_author_stats(self, books: List[BookProfile]) -> AuthorStats:
        """Compute author statistics"""
        years = [b.first_published_year for b in books if b.first_published_year]
        series_names = set(b.series_name for b in books if b.series_name)

        years_active = None
        if years:
            min_year, max_year = min(years), max(years)
            years_active = f"{min_year}-{max_year}" if min_year != max_year else str(min_year)

        return AuthorStats(
            total_works=len(books),
            series_count=len(series_names),
            most_popular_work=books[0].title if books else None,
            years_active=years_active,
        )

    # ==================== SERIES HELPERS ====================

    def _extract_series_premise(self, books: List[BookProfile]) -> Optional[str]:
        """Extract common premise from series books"""
        if not books:
            return None

        # Use first book's description as series premise
        first_book = min(books, key=lambda x: x.series_position or 999)
        return self._truncate_text(first_book.description, 300)

    # ==================== RAG DOCUMENT BUILDERS ====================

    def _build_book_rag_doc(self, title: str, authors: List[str],
                            description: Optional[str],
                            analysis: ContentAnalysis,
                            categories: List[str]) -> str:
        """Build RAG-optimized document for book"""
        sections = [
            f"Title: {title}",
            f"Author(s): {', '.join(authors)}",
            f"Genre: {', '.join(categories[:3])}",
            "",
            "Description:",
            (description[:800] + "...") if description and len(description) > 800
            else (description or "No description available."),
            "",
            "Themes:",
            ", ".join(analysis.key_themes) if analysis.key_themes else "Various themes",
            "",
            "Tone:",
            ", ".join(t.value for t in analysis.tone) if analysis.tone else "Mixed tone",
        ]

        if analysis.mood:
            sections.extend(["", f"Mood: {analysis.mood}"])

        if analysis.target_audience:
            sections.extend(["", f"Target Audience: {analysis.target_audience}"])

        return "\n".join(sections)

    def _build_author_rag_doc(self, name: str, bio: AuthorBio,
                              style: AuthorStyleProfile,
                              books: List[BookProfile]) -> str:
        """Build RAG-optimized document for author"""
        sections = [
            f"Author: {name}",
            "",
            "Biography:",
            bio.short_bio or bio.full_bio or "Biography not available.",
            "",
            "Writing Style:",
            style.description,
            "",
            "Genres:",
            ", ".join(style.genres[:5]) if style.genres else "Various",
            "",
            "Common Themes:",
            ", ".join(style.common_themes[:5]) if style.common_themes else "Various",
            "",
            f"Total Works: {len(books)}",
            "Notable Works:",
            ", ".join(b.title for b in books[:5]),
        ]

        return "\n".join(sections)

    def _build_series_rag_doc(self, series_name: str, books: List[SeriesBookEntry],
                              themes: List[str], author: str) -> str:
        """Build RAG-optimized document for series"""
        sections = [
            f"Series: {series_name}",
            f"Author: {author}",
            f"Number of Books: {len(books)}",
            "",
            "Reading Order:",
        ]

        for book in sorted(books, key=lambda x: x.position):
            sections.append(f"  {int(book.position)}. {book.title}")

        sections.extend([
            "",
            "Main Themes:",
            ", ".join(themes) if themes else "Various themes",
        ])

        return "\n".join(sections)


# Singleton instance
enrichment_engine = EnrichmentEngine()

