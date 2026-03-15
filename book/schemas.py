from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── Award ──────────────────────────────────────────────────────────────────────

class AwardBase(BaseModel):
    name: str
    year: int
    category: Optional[str] = None
    country: Optional[str] = None


class AwardCreate(AwardBase):
    pass


class AwardResponse(AwardBase):
    id: int
    model_config = {"from_attributes": True}


# ── Publisher ──────────────────────────────────────────────────────────────────

class PublisherBase(BaseModel):
    name: str
    location: Optional[str] = None
    year_founded: Optional[int] = None


class PublisherCreate(PublisherBase):
    pass


class PublisherResponse(PublisherBase):
    id: int
    model_config = {"from_attributes": True}


# ── Author ─────────────────────────────────────────────────────────────────────

class AuthorBase(BaseModel):
    name: str
    country: Optional[str] = None
    year_born: Optional[int] = None
    year_died: Optional[int] = None
    type_of_writer: Optional[str] = None


class AuthorCreate(AuthorBase):
    pass


class AuthorResponse(AuthorBase):
    id: int
    model_config = {"from_attributes": True}


class AuthorDetailResponse(AuthorResponse):
    """Author with their books and awards."""
    books: List["BookSummary"] = []
    awards: List[AwardResponse] = []


# ── Book ───────────────────────────────────────────────────────────────────────

class BookBase(BaseModel):
    isbn: str
    title: str
    year: int
    author_id: int
    publisher_id: Optional[int] = None


class BookCreate(BookBase):
    pass


class BookSummary(BaseModel):
    isbn: str
    title: str
    year: int
    model_config = {"from_attributes": True}


class BookResponse(BookBase):
    author_name: Optional[str] = None
    publisher_name: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class BookListResponse(BaseModel):
    items: List[BookResponse]
    total: int


class AuthorAwardCreate(BaseModel):
    author_id: int
    award_id: int


# Resolve forward references
AuthorDetailResponse.model_rebuild()

