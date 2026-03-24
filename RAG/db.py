import os
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = "rag_db"

BOOK_CACHE_COLLECTION = "book_cache"
READING_LIST_COLLECTION = "reading_list"
TASTE_PROFILES_COLLECTION = "taste_profiles"

_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None
_indexes_ready = False


async def _ensure_indexes(database: AsyncIOMotorDatabase) -> None:
    # Required unique and lookup indexes for reading lists.
    await database[READING_LIST_COLLECTION].create_index(
        [("user_id", 1), ("book_id", 1)],
        unique=True,
        name="ux_reading_list_user_book",
    )
    await database[READING_LIST_COLLECTION].create_index(
        [("user_id", 1)],
        name="ix_reading_list_user_id",
    )

    # Prevent duplicate cache entries for the same external book ID.
    await database[BOOK_CACHE_COLLECTION].create_index(
        [("book_id", 1)],
        unique=True,
        name="ux_book_cache_book_id",
    )


async def get_database() -> AsyncIOMotorDatabase:
    """Return the MongoDB database and ensure required indexes exist."""
    global _client, _database, _indexes_ready

    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URL)
        _database = _client[DB_NAME]

    if _database is None:
        raise RuntimeError("MongoDB database initialization failed")

    if not _indexes_ready:
        await _ensure_indexes(_database)
        _indexes_ready = True

    return _database


def get_book_cache_collection(database: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return database[BOOK_CACHE_COLLECTION]


def get_reading_list_collection(database: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return database[READING_LIST_COLLECTION]


def get_taste_profiles_collection(database: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return database[TASTE_PROFILES_COLLECTION]


async def close_database() -> None:
    """Close MongoDB client (call from FastAPI shutdown/lifespan)."""
    global _client, _database, _indexes_ready

    if _client is not None:
        _client.close()

    _client = None
    _database = None
    _indexes_ready = False

