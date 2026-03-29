from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List

class Author(BaseModel):
    author_id: str  # slugified name
    name: str
    bio: Optional[str] = None
    wikipedia_title: Optional[str] = None
    wikipedia_lang: Optional[str] = None
    wikipedia_url: Optional[str] = None
    book_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Book(BaseModel):
    book_id: str  # ISBN or UUID
    title: str
    authors: List[str] = Field(default_factory=list)
    author_ids: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    thumbnail: Optional[str] = None
    published_date: Optional[str] = None
    language: Optional[str] = None
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None
    source: str = "google_books"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)