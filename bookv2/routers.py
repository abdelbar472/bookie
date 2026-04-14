from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from .database import get_database
from .services import import_books_by_query, list_books_from_db, list_writers_from_db, ensure_book_and_writer
from .schemas import ImportBooksRequest, ResolveBookWriterRequest

router = APIRouter()


@router.get("/health")
async def health(db: AsyncIOMotorDatabase = Depends(get_database)):
    books = await db.books.count_documents({})
    authors = await db.authors.count_documents({})
    return {"status": "ok", "books": books, "authors": authors}


@router.post("/import/books")
async def import_books(
        payload: ImportBooksRequest,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Import books from Google Books API"""
    result = await import_books_by_query(db, payload.query.strip(), payload.max_results)
    return result


@router.get("/books/{book_id}")
async def get_book(book_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get single book"""
    book = await db.books.find_one({"book_id": book_id}, {"_id": 0})
    return book or {"error": "Not found"}


@router.get("/books")
async def list_books(
        q: str | None = None,
        skip: int = 0,
        limit: int = 20,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """List books from MongoDB"""
    return await list_books_from_db(db, skip=skip, limit=limit, q=q)


@router.get("/writers")
async def list_writers(
        q: str | None = None,
        skip: int = 0,
        limit: int = 20,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """List writers (authors) from MongoDB"""
    return await list_writers_from_db(db, skip=skip, limit=limit, q=q)


@router.get("/authors")
async def list_authors(
        q: str | None = None,
        skip: int = 0,
        limit: int = 20,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Backward-compatible alias for writers."""
    return await list_writers_from_db(db, skip=skip, limit=limit, q=q)


@router.post("/resolve")
async def resolve_book_or_writer(
        payload: ResolveBookWriterRequest,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    DB-first resolver.
    If book/writer is missing, fetch from Wikipedia and save.
    New books are forwarded to recommendation service.
    """
    return await ensure_book_and_writer(
        db=db,
        book_title=payload.book_title.strip() if payload.book_title else None,
        writer_name=payload.writer_name.strip() if payload.writer_name else None,
    )


@router.get("/authors/{author_id}")
async def get_author(author_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get author with their books"""
    author = await db.authors.find_one({"author_id": author_id}, {"_id": 0})
    if not author:
        return {"error": "Not found"}

    books = await db.books.find(
        {"book_id": {"$in": author.get("book_ids", [])}},
        {"_id": 0}
    ).to_list(length=50)

    return {**author, "books": books}


@router.get("/writers/{author_id}")
async def get_writer(author_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Backward-compatible writer route."""
    return await get_author(author_id, db)
