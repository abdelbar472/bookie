from fastapi import APIRouter
from typing import Optional

from .recommender import generate_recommendations
from .embedder import generate_query_embedding

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "recommendation"}

@router.post("/recommendations")
async def get_recommendations(
    user_id: Optional[str] = None,
    query: Optional[str] = None,
    book_id: Optional[str] = None,
    limit: int = 10
):
    """Get personalized recommendations"""
    result = await generate_recommendations(
        user_id=user_id,
        query=query,
        current_book_id=book_id,
        limit=limit
    )
    return result

@router.get("/recommendations/similar/{book_id}")
async def get_similar_books(
    book_id: str,
    user_id: Optional[str] = None,
    limit: int = 10
):
    """Find similar books"""
    return await generate_recommendations(
        current_book_id=book_id,
        user_id=user_id,
        limit=limit
    )

@router.get("/recommendations/for-you/{user_id}")
async def get_for_you(
    user_id: str,
    exclude_read: bool = True,
    limit: int = 10
):
    """Personalized feed for user"""
    return await generate_recommendations(
        user_id=user_id,
        exclude_read=exclude_read,
        limit=limit
    )

@router.post("/search")
async def semantic_search(
    q: str,
    limit: int = 20
):
    """Semantic search across books"""
    query_vector = generate_query_embedding(q)
    # Implementation...
    return {"query": q, "results": []}