from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class BookCache(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: str
    qdrant_id: int
    title: str
    authors: str
    description: str
    categories: list[str] = Field(default_factory=list)
    language: str
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None
    thumbnail: str
    source: Literal["google_books", "seed"]


class ReadingEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    book_id: str
    qdrant_id: int
    title: str
    authors: str
    status: Literal["read", "reading", "want_to_read"]
    rating: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    notes: Optional[str] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    interaction_weight: float = 0.8


class TasteProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    vector: list[float] = Field(min_length=384, max_length=384)
    book_count: int
    updated_at: datetime

