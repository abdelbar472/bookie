"""
Pydantic schemas for Book Service V3
Rich entity profiles optimized for RAG
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum


def utc_now():
    return datetime.now(timezone.utc)


# ==================== ENUMS ====================

class BookStatus(str, Enum):
    PUBLISHED = "published"
    UPCOMING = "upcoming"
    RARE = "rare"
    UNKNOWN = "unknown"


class ContentTone(str, Enum):
    DARK = "dark"
    LIGHT = "light"
    HUMOROUS = "humorous"
    SERIOUS = "serious"
    PHILOSOPHICAL = "philosophical"
    ACTION_PACKED = "action_packed"
    ROMANTIC = "romantic"
    MYSTERIOUS = "mysterious"
    MELANCHOLIC = "melancholic"
    HOPEFUL = "hopeful"


class ThemeCategory(str, Enum):
    IDENTITY = "identity"
    POWER = "power"
    LOVE = "love"
    WAR = "war"
    TECHNOLOGY = "technology"
    NATURE = "nature"
    SOCIETY = "society"
    COMING_OF_AGE = "coming_of_age"
    GOOD_VS_EVIL = "good_vs_evil"
    SURVIVAL = "survival"
    BETRAYAL = "betrayal"
    REDEMPTION = "redemption"
    FRIENDSHIP = "friendship"
    FAMILY = "family"
    MAGIC = "magic"
    MYSTERY = "mystery"
    HISTORICAL = "historical"
    HORROR = "horror"
    ADVENTURE = "adventure"
    POLITICS = "politics"
    RELIGION = "religion"
    DEATH = "death"
    TIME = "time"
    MEMORY = "memory"
    DYSTOPIA = "dystopia"  # for 1984, Brave New World, etc.
    COMING_OF_AGE_ALT = "coming of age"  # alternative spacing


# ==================== BOOK PROFILE ====================

class ContentAnalysis(BaseModel):
    """NLP-derived content understanding"""
    summary: Optional[str] = None
    key_themes: List[str] = Field(default_factory=list)
    dominant_themes: List[ThemeCategory] = Field(default_factory=list)
    tone: List[ContentTone] = Field(default_factory=list)
    mood: Optional[str] = None
    pacing: Optional[str] = None

    characters: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    time_period: Optional[str] = None

    content_warnings: List[str] = Field(default_factory=list)
    target_audience: Optional[str] = None


class QualityMetrics(BaseModel):
    """Data quality and completeness scoring"""
    description_quality: int = Field(0, ge=0, le=100)
    has_cover: bool = False
    has_isbn: bool = False
    has_page_count: bool = False
    has_publisher: bool = False
    has_language: bool = False
    source_count: int = Field(0, ge=0)
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)


class EditionEnriched(BaseModel):
    """Enhanced edition with quality metadata"""
    edition_id: str
    isbn_10: Optional[str] = None
    isbn_13: Optional[str] = None
    published_date: Optional[str] = None
    publisher: Optional[str] = None
    page_count: Optional[int] = None
    language: Optional[str] = None
    format: Optional[str] = None

    thumbnail: Optional[str] = None
    cover_large: Optional[str] = None

    availability_status: Optional[str] = None
    data_sources: List[str] = Field(default_factory=list)
    last_verified: datetime = Field(default_factory=utc_now)


class BookProfile(BaseModel):
    """Rich book profile for RAG - the core V3 entity"""
    model_config = ConfigDict(populate_by_name=True)

    # IDs
    work_id: str
    google_books_id: Optional[str] = None
    openlibrary_key: Optional[str] = None
    # Wikipedia
    wikipedia_url: Optional[str] = None
    wikipedia_title: Optional[str] = None
    wikipedia_lang: Optional[str] = None
    wikipedia_image_url: Optional[str] = None

    # Core Metadata
    title: str
    subtitle: Optional[str] = None
    title_variants: List[str] = Field(default_factory=list)

    # Authors
    authors: List[str]
    primary_author: str
    author_ids: List[str] = Field(default_factory=list)

    # Series
    series_name: Optional[str] = None
    series_position: Optional[float] = None

    # Content
    description: Optional[str] = None
    description_sources: List[str] = Field(default_factory=list)
    content_analysis: ContentAnalysis = Field(default_factory=ContentAnalysis)

    # Categorization
    genres: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    bisac_codes: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

    # Editions
    editions: List[EditionEnriched] = Field(default_factory=list)
    edition_count: int = 0

    # Quality & Metadata
    quality: QualityMetrics = Field(default_factory=QualityMetrics)
    first_published_year: Optional[int] = None
    original_language: Optional[str] = "en"

    # RAG-specific
    rag_document: Optional[str] = None
    embedding_id: Optional[str] = None

    # Tracking
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    enrichment_version: str = "3.0"

    def to_rag_text(self) -> str:
        """Generate RAG-optimized text representation"""
        if self.rag_document:
            return self.rag_document

        sections = [
            f"Title: {self.title}",
            f"Author(s): {', '.join(self.authors)}",
            f"Genre: {', '.join(self.genres[:3])}",
        ]

        if self.series_name:
            sections.append(f"Series: {self.series_name} (Book {self.series_position or '?'})")

        if self.wikipedia_url:
            sections.append(f"Wikipedia: {self.wikipedia_url}")

        sections.extend([
            "",
            "Description:",
            self.description[:1000] if self.description else "No description available.",
            "",
            "Themes:",
            ", ".join(self.content_analysis.key_themes) if self.content_analysis.key_themes else "Various themes",
            "",
            "Tone:",
            ", ".join(self.content_analysis.tone) if self.content_analysis.tone else "Mixed tone",
        ])

        return "\n".join(sections)


# ==================== AUTHOR PROFILE ====================

class AuthorBio(BaseModel):
    """Structured biography data"""
    short_bio: Optional[str] = None
    full_bio: Optional[str] = None
    early_life: Optional[str] = None
    career: Optional[str] = None
    personal_life: Optional[str] = None
    legacy: Optional[str] = None

    wikipedia_url: Optional[str] = None
    wikipedia_title: Optional[str] = None
    wikipedia_lang: str = "en"
    official_site: Optional[str] = None
    goodreads_author_url: Optional[str] = None


class AuthorStyleProfile(BaseModel):
    """Writing style analysis"""
    description: str = ""
    genres: List[str] = Field(default_factory=list)
    sub_genres: List[str] = Field(default_factory=list)
    tone: List[str] = Field(default_factory=list)
    common_themes: List[str] = Field(default_factory=list)
    writing_style: List[str] = Field(default_factory=list)
    narrative_voice: List[str] = Field(default_factory=list)

    influenced_by: List[str] = Field(default_factory=list)
    influenced: List[str] = Field(default_factory=list)
    similar_authors: List[str] = Field(default_factory=list)


class AuthorStats(BaseModel):
    """Computed statistics"""
    total_works: int = 0
    series_count: int = 0
    avg_rating: Optional[float] = None
    total_reviews: Optional[int] = None
    most_popular_work: Optional[str] = None
    years_active: Optional[str] = None


class AuthorProfile(BaseModel):
    """Rich author profile for RAG"""
    model_config = ConfigDict(populate_by_name=True)

    # IDs
    author_id: str
    name: str
    name_variants: List[str] = Field(default_factory=list)

    # Media
    image_url: Optional[str] = None
    image_urls: Dict[str, str] = Field(default_factory=dict)

    # Bio
    bio: AuthorBio = Field(default_factory=AuthorBio)

    # Style & Analysis
    style_profile: AuthorStyleProfile = Field(default_factory=AuthorStyleProfile)

    # Works
    notable_works: List[str] = Field(default_factory=list)
    series: List[str] = Field(default_factory=list)
    bibliography: Dict[str, List[str]] = Field(default_factory=dict)

    # Stats
    stats: AuthorStats = Field(default_factory=AuthorStats)

    # RAG
    rag_document: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    enrichment_version: str = "3.0"

    def to_rag_text(self) -> str:
        """Generate RAG-optimized text representation"""
        if self.rag_document:
            return self.rag_document

        sections = [
            f"Author: {self.name}",
            "",
            "Biography:",
            self.bio.short_bio or self.bio.full_bio or "Biography not available.",
            "",
            "Writing Style:",
            self.style_profile.description,
            "",
            "Genres:",
            ", ".join(self.style_profile.genres[:5]),
            "",
            "Notable Works:",
            ", ".join(self.notable_works[:5]),
        ]

        return "\n".join(sections)


# ==================== SERIES PROFILE ====================

class SeriesBookEntry(BaseModel):
    """Book within a series"""
    work_id: str
    title: str
    position: float
    published_year: Optional[int] = None
    is_core: bool = True
    summary: Optional[str] = None


class SeriesArc(BaseModel):
    """Story arc analysis"""
    arc_name: Optional[str] = None
    description: Optional[str] = None
    books_involved: List[str] = Field(default_factory=list)
    theme_progression: List[str] = Field(default_factory=list)


class SeriesProfile(BaseModel):
    """Rich series profile for RAG"""
    model_config = ConfigDict(populate_by_name=True)

    # IDs
    series_id: str
    series_name: str
    series_name_variants: List[str] = Field(default_factory=list)

    # Attribution
    primary_author: str
    author_id: str
    co_authors: List[str] = Field(default_factory=list)

    # Content
    description: Optional[str] = None
    premise: Optional[str] = None
    setting: Optional[str] = None
    time_span: Optional[str] = None

    # Structure
    books: List[SeriesBookEntry] = Field(default_factory=list)
    total_books: int = 0
    status: str = "ongoing"
    reading_order: List[str] = Field(default_factory=list)

    # Analysis
    main_themes: List[str] = Field(default_factory=list)
    character_arcs: List[str] = Field(default_factory=list)
    tone_evolution: Optional[str] = None
    arcs: List[SeriesArc] = Field(default_factory=list)

    # Recommendations
    similar_series: List[str] = Field(default_factory=list)
    next_if_you_liked: List[str] = Field(default_factory=list)

    # RAG
    rag_document: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    enrichment_version: str = "3.0"

    def to_rag_text(self) -> str:
        """Generate RAG-optimized text representation"""
        if self.rag_document:
            return self.rag_document

        sections = [
            f"Series: {self.series_name}",
            f"Author: {self.primary_author}",
            f"Books: {self.total_books}",
            f"Status: {self.status}",
            "",
            "Description:",
            self.description or "No description available.",
            "",
            "Reading Order:",
        ]

        for book in sorted(self.books, key=lambda x: x.position)[:10]:
            sections.append(f"{int(book.position)}. {book.title}")

        sections.extend([
            "",
            "Main Themes:",
            ", ".join(self.main_themes) if self.main_themes else "Various themes",
        ])

        return "\n".join(sections)


# ==================== API REQUEST/RESPONSE ====================

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., pattern="^(book|author|series)$")
    limit: int = Field(10, ge=1, le=50)
    skip_cache: bool = False


class BookSearchResponse(BaseModel):
    query: str
    count: int
    results: List[BookProfile]
    sources: List[str]
    from_cache: bool = False


class AuthorSearchResponse(BaseModel):
    query: str
    author: AuthorProfile
    books: List[BookProfile]
    total_books: int


class SeriesSearchResponse(BaseModel):
    query: str
    series: SeriesProfile
    books: List[BookProfile]


class HealthResponse(BaseModel):
    status: str
    version: str = "3.0.0"
    database: dict
    timestamp: datetime = Field(default_factory=utc_now)