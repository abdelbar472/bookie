from __future__ import annotations

import asyncio

from sqlmodel import select as sm_select

from .database import AsyncSessionLocal, create_db_and_tables
from .models import Author, AuthorAward, Award, Book, Publisher


async def _get_or_create_publisher(session, name: str, location: str, year_founded: int) -> Publisher:
    row = (
        await session.execute(sm_select(Publisher).where(Publisher.name == name))
    ).scalar_one_or_none()
    if row:
        return row
    row = Publisher(name=name, location=location, year_founded=year_founded)
    session.add(row)
    await session.flush()
    return row


async def _get_or_create_author(
    session,
    name: str,
    country: str,
    year_born: int,
    year_died: int | None,
    type_of_writer: str,
) -> Author:
    row = (
        await session.execute(sm_select(Author).where(Author.name == name))
    ).scalar_one_or_none()
    if row:
        return row
    row = Author(
        name=name,
        country=country,
        year_born=year_born,
        year_died=year_died,
        type_of_writer=type_of_writer,
    )
    session.add(row)
    await session.flush()
    return row


async def _get_or_create_award(
    session, name: str, year: int, category: str, country: str
) -> Award:
    row = (
        await session.execute(
            sm_select(Award).where(Award.name == name, Award.year == year)
        )
    ).scalar_one_or_none()
    if row:
        return row
    row = Award(name=name, year=year, category=category, country=country)
    session.add(row)
    await session.flush()
    return row


async def _link_author_award(session, author_id: int, award_id: int) -> None:
    link = (
        await session.execute(
            sm_select(AuthorAward).where(
                AuthorAward.author_id == author_id,
                AuthorAward.award_id == award_id,
            )
        )
    ).scalar_one_or_none()
    if link:
        return
    session.add(AuthorAward(author_id=author_id, award_id=award_id))
    await session.flush()


async def _get_or_create_book(
    session,
    isbn: str,
    title: str,
    year: int,
    author_id: int,
    publisher_id: int,
) -> Book:
    row = (
        await session.execute(sm_select(Book).where(Book.isbn == isbn))
    ).scalar_one_or_none()
    if row:
        return row
    row = Book(
        isbn=isbn,
        title=title,
        year=year,
        author_id=author_id,
        publisher_id=publisher_id,
    )
    session.add(row)
    await session.flush()
    return row


async def seed_books() -> None:
    await create_db_and_tables()

    async with AsyncSessionLocal() as session:
        penguin = await _get_or_create_publisher(session, "Penguin Books", "London, UK", 1935)
        harper = await _get_or_create_publisher(session, "HarperCollins", "New York, USA", 1989)

        orwell = await _get_or_create_author(
            session, "George Orwell", "UK", 1903, 1950, "Novelist"
        )
        atwood = await _get_or_create_author(
            session, "Margaret Atwood", "Canada", 1939, None, "Novelist"
        )

        nobel_1949 = await _get_or_create_award(
            session, "Nobel Prize in Literature", 1949, "Literature", "Sweden"
        )
        booker_2000 = await _get_or_create_award(
            session, "Booker Prize", 2000, "Fiction", "UK"
        )

        await _link_author_award(session, orwell.id, nobel_1949.id)
        await _link_author_award(session, atwood.id, booker_2000.id)

        await _get_or_create_book(
            session,
            "978-0-452-28423-4",
            "Nineteen Eighty-Four",
            1949,
            orwell.id,
            penguin.id,
        )
        await _get_or_create_book(
            session,
            "978-0-14-118776-1",
            "Animal Farm",
            1945,
            orwell.id,
            penguin.id,
        )
        await _get_or_create_book(
            session,
            "978-0-7710-0813-8",
            "The Handmaid's Tale",
            1985,
            atwood.id,
            harper.id,
        )

        await session.commit()

        books_total = (
            await session.execute(sm_select(Book))
        ).scalars().all()
        print(f"Seed complete. Total books in DB: {len(books_total)}")


if __name__ == "__main__":
    asyncio.run(seed_books())

