import logging
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, or_
from sqlmodel import select as sm_select

from .models import Book, Author, Publisher, Award, AuthorAward

logger = logging.getLogger(__name__)


# ── Publisher ──────────────────────────────────────────────────────────────────

async def create_publisher(
    session: AsyncSession,
    name: str,
    location: Optional[str] = None,
    year_founded: Optional[int] = None,
) -> Publisher:
    existing = (await session.execute(
        sm_select(Publisher).where(Publisher.name == name)
    )).scalar_one_or_none()
    if existing:
        raise ValueError(f"Publisher '{name}' already exists.")
    pub = Publisher(name=name, location=location, year_founded=year_founded)
    session.add(pub)
    await session.commit()
    await session.refresh(pub)
    logger.info("Created publisher: %s", name)
    return pub


async def get_publisher_by_name(session: AsyncSession, name: str) -> Optional[Publisher]:
    return (await session.execute(
        sm_select(Publisher).where(Publisher.name == name)
    )).scalar_one_or_none()


async def get_publisher_by_id(session: AsyncSession, pub_id: int) -> Optional[Publisher]:
    return (await session.execute(
        sm_select(Publisher).where(Publisher.id == pub_id)
    )).scalar_one_or_none()


async def list_publishers(
    session: AsyncSession, skip: int = 0, limit: int = 20
) -> Tuple[List[Publisher], int]:
    total = (await session.execute(select(func.count()).select_from(Publisher))).scalar_one()
    rows = (await session.execute(
        sm_select(Publisher).offset(skip).limit(limit).order_by(Publisher.name)
    )).scalars().all()
    return list(rows), total


# ── Award ──────────────────────────────────────────────────────────────────────

async def create_award(
    session: AsyncSession,
    name: str,
    year: int,
    category: Optional[str] = None,
    country: Optional[str] = None,
) -> Award:
    award = Award(name=name, year=year, category=category, country=country)
    session.add(award)
    await session.commit()
    await session.refresh(award)
    logger.info("Created award: %s (%s)", name, year)
    return award


async def get_award_by_id(session: AsyncSession, award_id: int) -> Optional[Award]:
    return (await session.execute(
        sm_select(Award).where(Award.id == award_id)
    )).scalar_one_or_none()


async def list_awards(
    session: AsyncSession, skip: int = 0, limit: int = 20
) -> Tuple[List[Award], int]:
    total = (await session.execute(select(func.count()).select_from(Award))).scalar_one()
    rows = (await session.execute(
        sm_select(Award).offset(skip).limit(limit).order_by(Award.year.desc())
    )).scalars().all()
    return list(rows), total


# ── Author ─────────────────────────────────────────────────────────────────────

async def create_author(
    session: AsyncSession,
    name: str,
    country: Optional[str] = None,
    year_born: Optional[int] = None,
    year_died: Optional[int] = None,
    type_of_writer: Optional[str] = None,
) -> Author:
    author = Author(
        name=name,
        country=country,
        year_born=year_born,
        year_died=year_died,
        type_of_writer=type_of_writer,
    )
    session.add(author)
    await session.commit()
    await session.refresh(author)
    logger.info("Created author: %s", name)
    return author


async def get_author_by_id(session: AsyncSession, author_id: int) -> Optional[Author]:
    return (await session.execute(
        sm_select(Author).where(Author.id == author_id)
    )).scalar_one_or_none()


async def list_authors(
    session: AsyncSession, skip: int = 0, limit: int = 20
) -> Tuple[List[Author], int]:
    total = (await session.execute(select(func.count()).select_from(Author))).scalar_one()
    rows = (await session.execute(
        sm_select(Author).offset(skip).limit(limit).order_by(Author.name)
    )).scalars().all()
    return list(rows), total


async def assign_award_to_author(
    session: AsyncSession, author_id: int, award_id: int
) -> AuthorAward:
    # verify both exist
    if not await get_author_by_id(session, author_id):
        raise ValueError(f"Author {author_id} not found.")
    if not await get_award_by_id(session, award_id):
        raise ValueError(f"Award {award_id} not found.")

    existing = (await session.execute(
        sm_select(AuthorAward).where(
            AuthorAward.author_id == author_id,
            AuthorAward.award_id == award_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise ValueError("Author already has this award.")

    link = AuthorAward(author_id=author_id, award_id=award_id)
    session.add(link)
    await session.commit()
    logger.info("Assigned award %s to author %s", award_id, author_id)
    return link


async def get_author_awards(session: AsyncSession, author_id: int) -> List[Award]:
    rows = (await session.execute(
        sm_select(Award)
        .join(AuthorAward, AuthorAward.award_id == Award.id)
        .where(AuthorAward.author_id == author_id)
        .order_by(Award.year.desc())
    )).scalars().all()
    return list(rows)


async def get_author_books(
    session: AsyncSession, author_id: int, skip: int = 0, limit: int = 20
) -> Tuple[List[Book], int]:
    total = (await session.execute(
        select(func.count()).select_from(Book).where(Book.author_id == author_id)
    )).scalar_one()
    rows = (await session.execute(
        sm_select(Book)
        .where(Book.author_id == author_id)
        .order_by(Book.year.desc())
        .offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


# ── Book ───────────────────────────────────────────────────────────────────────

async def create_book(
    session: AsyncSession,
    isbn: str,
    title: str,
    year: int,
    author_id: int,
    publisher_id: Optional[int] = None,
) -> Book:
    if not await get_author_by_id(session, author_id):
        raise ValueError(f"Author {author_id} not found.")
    if publisher_id and not await get_publisher_by_id(session, publisher_id):
        raise ValueError(f"Publisher {publisher_id} not found.")

    existing = (await session.execute(
        sm_select(Book).where(Book.isbn == isbn)
    )).scalar_one_or_none()
    if existing:
        raise ValueError(f"Book with ISBN '{isbn}' already exists.")

    book = Book(isbn=isbn, title=title, year=year, author_id=author_id, publisher_id=publisher_id)
    session.add(book)
    await session.commit()
    await session.refresh(book)
    logger.info("Created book: '%s' (%s)", title, isbn)
    return book


async def get_book_by_isbn(session: AsyncSession, isbn: str) -> Optional[Book]:
    return (await session.execute(
        sm_select(Book).where(Book.isbn == isbn)
    )).scalar_one_or_none()


async def list_books(
    session: AsyncSession, skip: int = 0, limit: int = 20
) -> Tuple[List[Book], int]:
    total = (await session.execute(select(func.count()).select_from(Book))).scalar_one()
    rows = (await session.execute(
        sm_select(Book).order_by(Book.year.desc(), Book.title).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def search_books(
    session: AsyncSession, query: str, skip: int = 0, limit: int = 20
) -> Tuple[List[Book], int]:
    pattern = f"%{query}%"
    condition = or_(Book.title.ilike(pattern), Book.isbn.ilike(pattern))
    total = (await session.execute(
        select(func.count()).select_from(Book).where(condition)
    )).scalar_one()
    rows = (await session.execute(
        sm_select(Book).where(condition).order_by(Book.year.desc()).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def enrich_book(session: AsyncSession, book: Book) -> dict:
    """Return a dict with author_name and publisher_name resolved."""
    author = await get_author_by_id(session, book.author_id)
    publisher = None
    if book.publisher_id:
        publisher = await get_publisher_by_id(session, book.publisher_id)
    return {
        "isbn": book.isbn,
        "title": book.title,
        "year": book.year,
        "author_id": book.author_id,
        "publisher_id": book.publisher_id,
        "author_name": author.name if author else None,
        "publisher_name": publisher.name if publisher else None,
        "created_at": book.created_at,
    }

