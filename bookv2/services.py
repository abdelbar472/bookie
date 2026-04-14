import re
from datetime import datetime
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .external_clients import (
    fetch_google_books,
    normalize_book,
    resolve_author,
    resolve_book_from_wikipedia,
)
from .rag_client import push_books_to_recommendation
from .social_client import notify_new_books


def _ci_exact(value: str) -> Dict:
    return {"$regex": f"^{re.escape(value.strip())}$", "$options": "i"}


async def list_books_from_db(
        db: AsyncIOMotorDatabase,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
) -> Dict:
    query = {}
    if q:
        query = {"$or": [{"title": {"$regex": re.escape(q), "$options": "i"}}, {"authors": {"$regex": re.escape(q), "$options": "i"}}]}

    total = await db.books.count_documents(query)
    cursor = db.books.find(query, {"_id": 0}).skip(skip).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"items": items, "total": total}


async def list_writers_from_db(
        db: AsyncIOMotorDatabase,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
) -> Dict:
    query = {}
    if q:
        query = {"name": {"$regex": re.escape(q), "$options": "i"}}

    total = await db.authors.count_documents(query)
    cursor = db.authors.find(query, {"_id": 0}).skip(skip).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"items": items, "total": total}


async def _upsert_book(db: AsyncIOMotorDatabase, book: Dict) -> bool:
    now = datetime.utcnow()
    book = {**book}
    book.setdefault("source", "google_books")
    book["updated_at"] = now

    result = await db.books.update_one(
        {"book_id": book["book_id"]},
        {"$set": book, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return result.upserted_id is not None


async def _upsert_author(db: AsyncIOMotorDatabase, author: Dict, book_ids: Optional[List[str]] = None) -> bool:
    now = datetime.utcnow()
    doc = {**author}
    doc.setdefault("source", "wikipedia")
    doc["updated_at"] = now

    update = {
        "$set": doc,
        "$setOnInsert": {"created_at": now, "book_ids": []},
    }
    if book_ids:
        update["$addToSet"] = {"book_ids": {"$each": [b for b in book_ids if b]}}

    result = await db.authors.update_one(
        {"author_id": doc["author_id"]},
        update,
        upsert=True,
    )
    return result.upserted_id is not None


async def _enrich_and_store_author_top_books(
        db: AsyncIOMotorDatabase,
        author_name: str,
        exclude_book_id: Optional[str] = None,
) -> List[Dict]:
    raw_items = await fetch_google_books(f'inauthor:"{author_name}"', max_results=5)
    inserted: List[Dict] = []

    for item in raw_items:
        normalized = normalize_book(item)
        if not normalized:
            continue
        if exclude_book_id and normalized["book_id"] == exclude_book_id:
            continue

        is_new = await _upsert_book(db, normalized)
        if is_new:
            inserted.append(normalized)

    return inserted


async def import_books_by_query(
        db: AsyncIOMotorDatabase,
        query: str,
        max_results: int = 10
) -> Dict:
    """Main import flow: fetch, enrich, store, notify"""

    raw_items = await fetch_google_books(query, max_results)

    imported_books = []
    new_authors = []

    for item in raw_items:
        book = normalize_book(item)
        if not book:
            continue

        existing = await db.books.find_one({"book_id": book["book_id"]})
        if existing:
            continue

        for idx, author_name in enumerate(book["authors"]):
            author_id = book["author_ids"][idx]
            existing_author = await db.authors.find_one({"author_id": author_id}, {"_id": 0})

            if not existing_author:
                author_data = await resolve_author(author_name)
                if author_data:
                    await _upsert_author(db, author_data, [book["book_id"]])
                    new_authors.append(author_data)
            else:
                await db.authors.update_one(
                    {"author_id": author_id},
                    {"$addToSet": {"book_ids": book["book_id"]}, "$set": {"updated_at": datetime.utcnow()}},
                )

        book_is_new = await _upsert_book(db, book)
        if book_is_new:
            imported_books.append(book)

    if imported_books:
        await push_books_to_recommendation(imported_books)
        await notify_new_books([b["book_id"] for b in imported_books])

    return {
        "imported_count": len(imported_books),
        "new_authors": len(new_authors),
        "books": imported_books
    }


async def ensure_book_and_writer(
        db: AsyncIOMotorDatabase,
        book_title: Optional[str],
        writer_name: Optional[str],
) -> Dict:
    """
    DB-first resolver:
    1) return existing book/writer from DB,
    2) fallback to Wikipedia for missing entities,
    3) push new books to recommender,
    4) if both are new, ingest top-5 books for that writer.
    """
    if not (book_title or writer_name):
        return {"error": "book_title or writer_name is required"}

    created_books: List[Dict] = []
    created_writer = None

    existing_book = None
    if book_title:
        existing_book = await db.books.find_one(
            {"$or": [{"book_id": _ci_exact(book_title)}, {"title": _ci_exact(book_title)}]},
            {"_id": 0},
        )

    existing_writer = None
    if writer_name:
        existing_writer = await db.authors.find_one({"name": _ci_exact(writer_name)}, {"_id": 0})

    book_is_new = False
    writer_is_new = False

    if not existing_book and book_title:
        wiki_book = await resolve_book_from_wikipedia(book_title)
        if wiki_book:
            if writer_name and not wiki_book.get("authors"):
                wiki_book["authors"] = [writer_name]
                writer_slug = re.sub(r"[^a-z0-9]+", "-", writer_name.lower()).strip("-") or "unknown-author"
                wiki_book["author_ids"] = [writer_slug]

            book_is_new = await _upsert_book(db, wiki_book)
            existing_book = await db.books.find_one({"book_id": wiki_book["book_id"]}, {"_id": 0})
            if book_is_new and existing_book:
                created_books.append(existing_book)

            if not writer_name and existing_book and existing_book.get("authors"):
                writer_name = existing_book["authors"][0]

    if not existing_writer and writer_name:
        author_data = await resolve_author(writer_name)
        if author_data:
            links = [existing_book["book_id"]] if existing_book else []
            writer_is_new = await _upsert_author(db, author_data, links)
            existing_writer = await db.authors.find_one({"author_id": author_data["author_id"]}, {"_id": 0})
            if writer_is_new:
                created_writer = existing_writer

    if existing_book and existing_writer:
        await db.authors.update_one(
            {"author_id": existing_writer["author_id"]},
            {"$addToSet": {"book_ids": existing_book["book_id"]}, "$set": {"updated_at": datetime.utcnow()}},
        )

    if book_is_new and writer_is_new and writer_name:
        extra_books = await _enrich_and_store_author_top_books(
            db,
            writer_name,
            exclude_book_id=existing_book["book_id"] if existing_book else None,
        )
        if extra_books:
            for book in extra_books:
                await db.authors.update_one(
                    {"author_id": existing_writer["author_id"]},
                    {"$addToSet": {"book_ids": book["book_id"]}, "$set": {"updated_at": datetime.utcnow()}},
                )
            created_books.extend(extra_books)

    if created_books:
        await push_books_to_recommendation(created_books)
        await notify_new_books([b["book_id"] for b in created_books])

    return {
        "book": existing_book,
        "writer": existing_writer,
        "book_was_new": book_is_new,
        "writer_was_new": writer_is_new,
        "top5_added": max(0, len(created_books) - (1 if book_is_new else 0)),
        "created_books": created_books,
        "created_writer": created_writer,
    }
