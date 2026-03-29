from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from .database import get_database
from .services import import_books_by_query

router = APIRouter()


@router.get("/health")
async def health(db: AsyncIOMotorDatabase = Depends(get_database)):
    books = await db.books.count_documents({})
    authors = await db.authors.count_documents({})
    return {"status": "ok", "books": books, "authors": authors}


@router.post("/import/books")
async def import_books(
        query: str,
        max_results: int = 10,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Import books from Google Books API"""
    result = await import_books_by_query(db, query, max_results)
    return result


@router.get("/books/{book_id}")
async def get_book(book_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get single book"""
    book = await db.books.find_one({"book_id": book_id}, {"_id": 0})
    return book or {"error": "Not found"}


@router.get("/books")
async def list_books(
        skip: int = 0,
        limit: int = 20,
        db: AsyncIOMotorDatabase = Depends(get_database)
):
    """List books"""
    cursor = db.books.find({}, {"_id": 0}).skip(skip).limit(limit)
    books = await cursor.to_list(length=limit)
    return {"books": books, "count": len(books)}


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