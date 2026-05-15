from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Dict, Any
from models.common import ThemeCategory, ContentTone


class ContentAnalysis(BaseModel):
    key_themes: List[str] = Field(default_factory=list)
    dominant_themes: List[ThemeCategory] = Field(default_factory=list)
    tone: List[ContentTone] = Field(default_factory=list)
    mood: str = "neutral"
    pacing: str = "moderate"
    target_audience: Optional[str] = None
    characters: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)


class QualityMetrics(BaseModel):
    description_quality: int = 0
    has_cover: bool = False
    has_isbn: bool = False
    has_page_count: bool = False
    source_count: int = 0
    confidence_score: float = 0.0


class Edition(BaseModel):
    edition_id: str
    isbn_10: Optional[str] = None
    isbn_13: Optional[str] = None
    published_date: Optional[str] = None
    publisher: Optional[str] = None
    page_count: Optional[int] = None
    language: Optional[str] = None
    format: Optional[str] = None
    thumbnail: Optional[str] = None
    source: str = "unknown"


class BookProfile(BaseModel):
    work_id: str = Field(..., description="Unique work identifier")
    title: str
    subtitle: Optional[str] = None

    primary_author: str
    authors: List[str]

    description: Optional[str] = None
    description_sources: List[str] = Field(default_factory=list)

    first_published_year: Optional[int] = None
    original_language: str = "en"

    series_name: Optional[str] = None
    series_position: Optional[float] = None
    series_id: Optional[str] = None

    genres: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

    content_analysis: ContentAnalysis = Field(default_factory=ContentAnalysis)
    quality: QualityMetrics = Field(default_factory=QualityMetrics)

    editions: List[Edition] = Field(default_factory=list)
    edition_count: int = 0

    image_url: Optional[str] = None
    wikipedia_url: Optional[str] = None
    wikipedia_title: Optional[str] = None

    rag_document: str = ""
    sources: List[str] = Field(default_factory=list)
    last_enriched_at: datetime = Field(default_factory=datetime.utcnow)

    meta: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }