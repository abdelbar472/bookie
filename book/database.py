# database.py
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import logging
from typing import Optional, Dict

from config import settings
from models.book import BookProfile
from models.author import AuthorProfile
from models.series import SeriesProfile

logger = logging.getLogger(__name__)


class Database:
    client: AsyncIOMotorClient = None
    db = None

    @classmethod
    async def connect(cls):
        try:
            cls.client = AsyncIOMotorClient(settings.MONGODB_URL)
            cls.db = cls.client[settings.MONGODB_DB_NAME]
            await cls.client.admin.command('ping')
            logger.info(f"✅ Connected to MongoDB: {settings.MONGODB_DB_NAME}")
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise

    @classmethod
    async def close(cls):
        if cls.client:
            cls.client.close()
            logger.info("✅ MongoDB connection closed.")

    # ====================== BOOKS ======================
    @classmethod
    async def save_book(cls, book: BookProfile):
        collection = cls.db[settings.BOOKS_COLLECTION]
        data = book.model_dump(by_alias=True, exclude_none=True)
        data["last_enriched_at"] = datetime.utcnow()

        await collection.update_one(
            {"_id": book.work_id},
            {"$set": data},
            upsert=True
        )
        logger.info(f"Saved book: {book.title}")

    @classmethod
    async def get_book(cls, work_id: str) -> Optional[Dict]:
        return await cls.db[settings.BOOKS_COLLECTION].find_one({"_id": work_id})

    @classmethod
    async def list_books(cls, skip: int = 0, limit: int = 100) -> list:
        cursor = cls.db[settings.BOOKS_COLLECTION].find().skip(skip).limit(limit)
        return await cursor.to_list(length=None)

    @classmethod
    async def search_books(cls, query: str, skip: int = 0, limit: int = 100) -> list:
        # Use text search if index exists
        cursor = cls.db[settings.BOOKS_COLLECTION].find(
            {"$text": {"$search": query}}
        ).skip(skip).limit(limit)
        return await cursor.to_list(length=None)

    # ====================== AUTHORS ======================
    @classmethod
    async def save_author(cls, author: AuthorProfile):
        collection = cls.db[settings.AUTHORS_COLLECTION]
        data = author.model_dump(by_alias=True, exclude_none=True)
        data["last_enriched_at"] = datetime.utcnow()

        await collection.update_one(
            {"_id": author.author_id},
            {"$set": data},
            upsert=True
        )
        logger.info(f"Saved author: {author.name}")

    @classmethod
    async def get_author(cls, author_id: str) -> Optional[Dict]:
        return await cls.db[settings.AUTHORS_COLLECTION].find_one({"_id": author_id})

    # ====================== SERIES ======================
    @classmethod
    async def save_series(cls, series: SeriesProfile):
        collection = cls.db[settings.SERIES_COLLECTION]
        data = series.model_dump(by_alias=True, exclude_none=True)
        data["last_enriched_at"] = datetime.utcnow()

        await collection.update_one(
            {"_id": series.series_id},
            {"$set": data},
            upsert=True
        )
        logger.info(f"Saved series: {series.series_name}")

    @classmethod
    async def get_series(cls, series_id: str) -> Optional[Dict]:
        return await cls.db[settings.SERIES_COLLECTION].find_one({"_id": series_id})


# Global instance
db = Database()