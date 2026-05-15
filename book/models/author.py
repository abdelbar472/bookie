from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from models.book import BookProfile


class AuthorBio(BaseModel):
    short_bio: Optional[str] = None
    full_bio: Optional[str] = None
    wikipedia_url: Optional[str] = None
    wikipedia_title: Optional[str] = None
    wikipedia_lang: str = "en"


class AuthorStyleProfile(BaseModel):
    description: str = ""
    genres: List[str] = Field(default_factory=list)
    common_themes: List[str] = Field(default_factory=list)
    tone: List[str] = Field(default_factory=list)


class AuthorStats(BaseModel):
    total_works: int = 0
    series_count: int = 0
    most_popular_work: Optional[str] = None
    years_active: Optional[str] = None


class AuthorProfile(BaseModel):
    author_id: str
    name: str
    name_variants: List[str] = Field(default_factory=list)

    bio: AuthorBio = Field(default_factory=AuthorBio)
    image_url: Optional[str] = None

    style_profile: AuthorStyleProfile = Field(default_factory=AuthorStyleProfile)
    stats: AuthorStats = Field(default_factory=AuthorStats)

    notable_works: List[str] = Field(default_factory=list)
    books: List[BookProfile] = Field(default_factory=list)  # Add books field
    series: List[str] = Field(default_factory=list)

    rag_document: str = ""
    last_enriched_at: datetime = Field(default_factory=datetime.utcnow)
    sources: List[str] = Field(default_factory=list)