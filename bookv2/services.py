from typing import Dict
from motor.motor_asyncio import AsyncIOMotorDatabase

from .external_clients import (
    fetch_google_books, normalize_book, resolve_author
)
from .rag_client import push_books_to_recommendation
from .social_client import notify_new_books


async def import_books_by_query(
        db: AsyncIOMotorDatabase,
        query: str,
        max_results: int = 10
) -> Dict:
    """Main import flow: fetch, enrich, store, notify"""

    # 1. Fetch from Google Books
    raw_items = await fetch_google_books(query, max_results)

    imported_books = []
    new_authors = []

    for item in raw_items:
        # Normalize
        book = normalize_book(item)
        if not book:
            continue

        # Check if exists
        existing = await db.books.find_one({"book_id": book["book_id"]})
        if existing:
            continue

        # Resolve authors (Wikipedia enrichment)
        for author_name in book["authors"]:
            author_id = book["author_ids"][book["authors"].index(author_name)]

            # Check if author exists
            existing_author = await db.authors.find_one({"author_id": author_id})

            if not existing_author:
                # Resolve via Wikipedia
                author_data = await resolve_author(author_name)

                if author_data:
                    # Fetch 5 more books for this new author
                    author_books = await fetch_google_books(
                        f'inauthor:"{author_name}"',
                        max_results=5
                    )

                    author_book_ids = []
                    for ab in author_books:
                        ab_norm = normalize_book(ab)
                        if ab_norm and ab_norm["book_id"] != book["book_id"]:
                            # Upsert avoids duplicate key failures when Google returns overlapping titles.
                            extra_result = await db.books.update_one(
                                {"book_id": ab_norm["book_id"]},
                                {"$set": ab_norm},
                                upsert=True,
                            )
                            if extra_result.upserted_id is not None:
                                imported_books.append(ab_norm)
                            author_book_ids.append(ab_norm["book_id"])

                    author_data["book_ids"] = [book["book_id"]] + author_book_ids
                    await db.authors.update_one(
                        {"author_id": author_id},
                        {
                            "$set": {k: v for k, v in author_data.items() if k != "book_ids"},
                            "$addToSet": {"book_ids": {"$each": author_data["book_ids"]}},
                        },
                        upsert=True,
                    )
                    new_authors.append(author_data)
            else:
                await db.authors.update_one(
                    {"author_id": author_id},
                    {"$addToSet": {"book_ids": book["book_id"]}},
                )

        # Store main book
        book_result = await db.books.update_one(
            {"book_id": book["book_id"]},
            {"$set": book},
            upsert=True,
        )
        if book_result.upserted_id is not None:
            imported_books.append(book)

    # Stream to Recommendation service (async)
    if imported_books:
        await push_books_to_recommendation(imported_books)
        await notify_new_books([b["book_id"] for b in imported_books])

    return {
        "imported_count": len(imported_books),
        "new_authors": len(new_authors),
        "books": imported_books
    }