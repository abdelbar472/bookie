from datetime import datetime

from pydantic import BaseModel, Field


class ImportBooksRequest(BaseModel):
    query: str = Field(min_length=1)
    max_results: int = Field(default=10, ge=1, le=40)


class ImportAuthorsRequest(BaseModel):
    name: str = Field(min_length=1)
    max_results: int = Field(default=10, ge=1, le=50)


class BookResponse(BaseModel):
    book_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    author_ids: list[str] = Field(default_factory=list)
    description: str = ""
    categories: list[str] = Field(default_factory=list)
    language: str | None = None
    published_date: str | None = None
    isbn: str | None = None
    thumbnail: str | None = None
    average_rating: float | None = None
    ratings_count: int | None = None
    author_style: str | None = None
    source: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class AuthorResponse(BaseModel):
    author_id: str
    name: str
    bio: str | None = None
    style_text: str | None = None
    wikipedia_title: str | None = None
    wikipedia_lang: str | None = None
    wikipedia_url: str | None = None
    book_ids: list[str] = Field(default_factory=list)
    source: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ImportResponse(BaseModel):
    imported: int
    updated: int
    rag_indexed: int = 0
    message: str | None = None
    items: list[dict]


class BookListResponse(BaseModel):
    items: list[BookResponse]
    total: int


class AuthorListResponse(BaseModel):
    items: list[AuthorResponse]
    total: int

