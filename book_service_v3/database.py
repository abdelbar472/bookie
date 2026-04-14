"""
MongoDB connection management with graceful degradation
"""
import logging
from typing import Optional

import motor.motor_asyncio
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from .config import settings

logger = logging.getLogger(__name__)


class DatabaseUnavailableError(Exception):
    """Raised when MongoDB is not reachable or not initialized."""
    pass


class Database:
    client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
    is_connected: bool = False


db = Database()


async def connect_to_mongo() -> bool:
    """
    Establish connection to MongoDB with timeout
    Returns True if connected, False otherwise
    """
    logger.info("Connecting to MongoDB at %s...", settings.MONGODB_URL)

    try:
        client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=5000,
            maxPoolSize=10,
            minPoolSize=1,
        )

        # Verify connection
        await client.admin.command("ping")

        db.client = client
        db.is_connected = True

        # Create indexes
        await _create_indexes()

        logger.info("✓ Connected to MongoDB successfully!")
        return True

    except (PyMongoError, ServerSelectionTimeoutError) as exc:
        logger.warning("✗ MongoDB unavailable: %s", exc)
        db.client = None
        db.is_connected = False
        return False


async def close_mongo_connection() -> None:
    """Close MongoDB connection"""
    logger.info("Closing MongoDB connection...")
    if db.client is not None:
        db.client.close()
        db.is_connected = False
    logger.info("MongoDB connection closed.")


async def _create_indexes() -> None:
    """Create database indexes for performance"""
    if not db.is_connected:
        return

    try:
        book_db = db.client[settings.DATABASE_NAME]

        # Book profiles indexes
        await book_db.book_profiles.create_index("work_id", unique=True)
        await book_db.book_profiles.create_index("primary_author")
        await book_db.book_profiles.create_index("series_name")
        await book_db.book_profiles.create_index("genres")
        await book_db.book_profiles.create_index([("title", "text"), ("description", "text")])

        # Author profiles indexes
        await book_db.author_profiles.create_index("author_id", unique=True)
        await book_db.author_profiles.create_index("name")

        # Series profiles indexes
        await book_db.series_profiles.create_index("series_id", unique=True)
        await book_db.series_profiles.create_index("primary_author")

        logger.info("Database indexes created.")

    except Exception as e:
        logger.error("Failed to create indexes: %s", e)


def get_db() -> motor.motor_asyncio.AsyncIOMotorDatabase:
    """Get database instance"""
    if not db.is_connected or db.client is None:
        raise DatabaseUnavailableError("MongoDB is not available")
    return db.client[settings.DATABASE_NAME]


def get_collection(collection_name: str) -> motor.motor_asyncio.AsyncIOMotorCollection:
    """Get specific collection"""
    return get_db()[collection_name]


def check_db_health() -> dict:
    """Health check for database"""
    return {
        "connected": db.is_connected,
        "database": settings.DATABASE_NAME if db.is_connected else None
    }