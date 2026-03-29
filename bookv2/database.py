from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import settings

BOOKS_COLLECTION = "books"
AUTHORS_COLLECTION = "authors"

_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None
_indexes_ready = False


async def _ensure_indexes(database: AsyncIOMotorDatabase) -> None:
    await database[BOOKS_COLLECTION].create_index([("book_id", 1)], unique=True, name="ux_books_book_id")
    await database[BOOKS_COLLECTION].create_index([("isbn", 1)], unique=True, sparse=True, name="ux_books_isbn")
    await database[BOOKS_COLLECTION].create_index([("title", "text"), ("authors", "text")], name="ix_books_text")

    await database[AUTHORS_COLLECTION].create_index([("author_id", 1)], unique=True, name="ux_authors_author_id")
    await database[AUTHORS_COLLECTION].create_index([("name", 1)], name="ix_authors_name")


async def get_database() -> AsyncIOMotorDatabase:
    global _client, _database, _indexes_ready

    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGODB_URL)
        _database = _client[settings.MONGODB_DB_NAME]

    if _database is None:
        raise RuntimeError("MongoDB database initialization failed")

    if not _indexes_ready:
        await _ensure_indexes(_database)
        _indexes_ready = True

    return _database


async def close_database() -> None:
    global _client, _database, _indexes_ready

    if _client is not None:
        _client.close()

    _client = None
    _database = None
    _indexes_ready = False

