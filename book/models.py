from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


class Award(SQLModel, table=True):
    """An award that can be won by an author."""
    __tablename__ = "awards"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=255)
    year: int
    category: Optional[str] = Field(default=None, max_length=255)
    country: Optional[str] = Field(default=None, max_length=100)

    # back-link
    author_awards: List["AuthorAward"] = Relationship(back_populates="award")


class Publisher(SQLModel, table=True):
    """A book publisher."""
    __tablename__ = "publishers"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True, max_length=255)
    location: Optional[str] = Field(default=None, max_length=255)
    year_founded: Optional[int] = Field(default=None)

    books: List["Book"] = Relationship(back_populates="publisher_rel")


class Author(SQLModel, table=True):
    """A book author."""
    __tablename__ = "authors"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=255)
    country: Optional[str] = Field(default=None, max_length=100)
    year_born: Optional[int] = Field(default=None)
    year_died: Optional[int] = Field(default=None)
    type_of_writer: Optional[str] = Field(default=None, max_length=100)

    books: List["Book"] = Relationship(back_populates="author")
    author_awards: List["AuthorAward"] = Relationship(back_populates="author")


class AuthorAward(SQLModel, table=True):
    """Many-to-many: Author ↔ Award."""
    __tablename__ = "author_awards"

    author_id: int = Field(foreign_key="authors.id", primary_key=True)
    award_id: int = Field(foreign_key="awards.id", primary_key=True)

    author: Optional[Author] = Relationship(back_populates="author_awards")
    award: Optional[Award] = Relationship(back_populates="author_awards")


class Book(SQLModel, table=True):
    """A book record – added internally, never directly by end-users."""
    __tablename__ = "books"

    isbn: str = Field(primary_key=True, max_length=20)
    title: str = Field(index=True, max_length=500)
    year: int
    author_id: int = Field(foreign_key="authors.id", index=True)
    publisher_id: Optional[int] = Field(default=None, foreign_key="publishers.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    author: Optional[Author] = Relationship(back_populates="books")
    publisher_rel: Optional[Publisher] = Relationship(back_populates="books")

class BookAutherAward(SQLModel, table=True):
    """Many-to-many: Book ↔ AuthorAward."""
    __tablename__ = "book_author_awards"

    book_isbn: str = Field(foreign_key="books.isbn", primary_key=True)
    author_id: int = Field(foreign_key="authors.id", primary_key=True)
    award_id: int = Field(foreign_key="awards.id", primary_key=True)

    book: Optional[Book] = Relationship()
    # Keep this as a plain link table; there is no direct FK to author_awards.
