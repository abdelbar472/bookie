"""Qdrant client lifecycle and access helpers for retrieval."""

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from rag_service.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    qdrant: Optional[QdrantClient] = None

    @classmethod
    async def connect(cls):
        await cls._connect_qdrant()

    @classmethod
    async def _connect_qdrant(cls):
        try:
            if settings.QDRANT_API_KEY:
                cls.qdrant = QdrantClient(
                    url=f"https://{settings.QDRANT_HOST}",
                    api_key=settings.QDRANT_API_KEY,
                )
            else:
                cls.qdrant = QdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                )

            cls._ensure_collection()
            logger.info("Connected to Qdrant")
        except Exception as exc:
            logger.error("Qdrant connection failed: %s", exc)
            cls.qdrant = None

    @classmethod
    def _ensure_collection(cls):
        if not cls.qdrant:
            return
        try:
            collections = cls.qdrant.get_collections().collections
            collection_names = [c.name for c in collections]
            if settings.QDRANT_COLLECTION_NAME not in collection_names:
                cls.qdrant.create_collection(
                    collection_name=settings.QDRANT_COLLECTION_NAME,
                    vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSION, distance=Distance.COSINE),
                )
                logger.info("Created collection: %s", settings.QDRANT_COLLECTION_NAME)
        except Exception as exc:
            logger.error("Failed to ensure collection: %s", exc)

    @classmethod
    async def close(cls):
        logger.info("Database connections closed")


def get_qdrant() -> QdrantClient:
    if DatabaseManager.qdrant is None:
        raise RuntimeError("Qdrant not connected")
    return DatabaseManager.qdrant

