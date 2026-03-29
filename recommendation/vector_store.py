import logging
from typing import List, Optional
import uuid
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models

from .config import settings
from .embedder import generate_book_embeddings

logger = logging.getLogger(__name__)
_client = None


def point_id_from_book_id(book_id: str) -> str:
    """Generate stable UUID accepted by Qdrant for string book identifiers."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"book:{book_id}"))


async def init_qdrant():
    global _client
    _client = AsyncQdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT
    )

    # Create collection with multiple vectors
    try:
        await _client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config={
                "content": qdrant_models.VectorParams(
                    size=settings.VECTOR_DIM,
                    distance=qdrant_models.Distance.COSINE
                ),
                "author_style": qdrant_models.VectorParams(
                    size=settings.VECTOR_DIM,
                    distance=qdrant_models.Distance.COSINE
                ),
                "user_preference": qdrant_models.VectorParams(
                    size=settings.VECTOR_DIM,
                    distance=qdrant_models.Distance.COSINE
                )
            }
        )
        logger.info("Created Qdrant collection")
    except Exception as e:
        if "already exists" in str(e):
            logger.info("Collection already exists")
        else:
            raise


async def index_books(books: List[dict]):
    """Index books with embeddings"""
    if _client is None:
        raise RuntimeError("Qdrant client is not initialized")

    points = []

    for book in books:
        # Generate embeddings
        embeddings = generate_book_embeddings(book)

        points.append(qdrant_models.PointStruct(
            id=point_id_from_book_id(book["book_id"]),
            vector={
                "content": embeddings["content"],
                "author_style": embeddings["author_style"],
                "user_preference": embeddings["content"],  # Default, personalized later
            },
            payload={
                "book_id": book["book_id"],
                "title": book["title"],
                "authors": book.get("authors", []),
                "author_ids": book.get("author_ids", []),
                "categories": book.get("categories", []),
                "description": book.get("description", "")[:200],
                "thumbnail": book.get("thumbnail", ""),
                "average_rating": book.get("average_rating", 0),
            }
        ))

    if points:
        await _client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points
        )
        logger.info(f"Indexed {len(points)} books")


async def search_recommendations(
        content_vector: Optional[List[float]] = None,
        author_style_vector: Optional[List[float]] = None,
        user_vector: Optional[List[float]] = None,
        filter_conditions: Optional[dict] = None,
        limit: int = 20
) -> List[dict]:
    """Multi-vector hybrid search"""
    if _client is None:
        raise RuntimeError("Qdrant client is not initialized")

    prefetches = []

    if content_vector:
        prefetches.append(qdrant_models.Prefetch(
            query=content_vector,
            using="content",
            limit=limit * 2,
        ))

    if author_style_vector:
        prefetches.append(qdrant_models.Prefetch(
            query=author_style_vector,
            using="author_style",
            limit=limit * 2,
        ))

    if user_vector:
        prefetches.append(qdrant_models.Prefetch(
            query=user_vector,
            using="user_preference",
            limit=limit * 2,
        ))

    if not prefetches:
        return []

    results = await _client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        prefetch=prefetches,
        query=qdrant_models.FusionQuery(fusion=qdrant_models.Fusion.RRF),
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "id": r.payload.get("book_id") if isinstance(r.payload, dict) else str(r.id),
            "score": r.score,
            "payload": r.payload,
        }
        for r in results.points
    ]
