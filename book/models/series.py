from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional


class SeriesBookEntry(BaseModel):
    work_id: str
    title: str
    position: float
    published_year: Optional[int] = None
    summary: Optional[str] = None


class SeriesProfile(BaseModel):
    series_id: str
    series_name: str
    primary_author: str
    author_id: str

    description: Optional[str] = None
    premise: Optional[str] = None

    books: List[SeriesBookEntry] = Field(default_factory=list)
    total_books: int = 0
    reading_order: List[str] = Field(default_factory=list)

    main_themes: List[str] = Field(default_factory=list)

    image_url: Optional[str] = None
    wikipedia_url: Optional[str] = None

    rag_document: str = ""
    last_enriched_at: datetime = Field(default_factory=datetime.utcnow)
    sources: List[str] = Field(default_factory=list)