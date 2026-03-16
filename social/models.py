from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BookLike(SQLModel, table=True):
    __tablename__ = "book_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "isbn", name="uq_book_like_user_isbn"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    isbn: str = Field(index=True, max_length=20)
    created_at: datetime = Field(default_factory=utc_now)


class BookRating(SQLModel, table=True):
    __tablename__ = "book_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "isbn", name="uq_book_rating_user_isbn"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    isbn: str = Field(index=True, max_length=20)
    rating: float = Field(ge=0.5, le=5.0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class BookReview(SQLModel, table=True):
    __tablename__ = "book_reviews"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    isbn: str = Field(index=True, max_length=20)
    parent_review_id: Optional[int] = Field(default=None, foreign_key="book_reviews.id", index=True)
    title: str = Field(max_length=200)
    content: str = Field(max_length=4000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReviewLike(SQLModel, table=True):
    __tablename__ = "review_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "review_id", name="uq_review_like_user_review"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    review_id: int = Field(foreign_key="book_reviews.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)


class Shelf(SQLModel, table=True):
    __tablename__ = "shelves"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_shelf_user_name"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    name: str = Field(max_length=120)
    visibility: str = Field(default="private", max_length=20)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ShelfItem(SQLModel, table=True):
    __tablename__ = "shelf_items"
    __table_args__ = (
        UniqueConstraint("shelf_id", "isbn", name="uq_shelf_item_shelf_isbn"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    shelf_id: int = Field(foreign_key="shelves.id", index=True)
    isbn: str = Field(index=True, max_length=20)
    position: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
