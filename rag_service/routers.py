"""FastAPI routers for RAG Service."""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from .services import IndexingService, RecommendationService, SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag")


@router.get("/search")
async def semantic_search(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
    type: Optional[str] = Query(None, description="Filter: book, author, series"),
    genre: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
):
    try:
        return await SearchService.semantic_search(
            query=q,
            top_k=top_k,
            entity_type=type,
            genre=genre,
            author=author,
        )
    except Exception as exc:
        logger.error("Search failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/similar/{work_id}")
async def find_similar(work_id: str, top_k: int = Query(5, ge=1, le=20)):
    try:
        return await SearchService.find_similar_books(work_id, top_k)
    except Exception as exc:
        logger.error("Similar search failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/thematic")
async def thematic_search(themes: List[str], top_k: int = Query(10, ge=1, le=50)):
    try:
        return await SearchService.thematic_search(themes, top_k)
    except Exception as exc:
        logger.error("Thematic search failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/recommend")
async def get_recommendations(
    history: List[str],
    top_k: int = Query(10, ge=1, le=50),
    diversify: bool = Query(True),
):
    try:
        return await RecommendationService.get_recommendations(
            user_history=history,
            top_k=top_k,
            diversify=diversify,
        )
    except Exception as exc:
        logger.error("Recommendation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stats")
async def get_stats():
    try:
        return await IndexingService.get_stats()
    except Exception as exc:
        logger.error("Stats failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def health_check():
    from .vector_store import vector_store

    try:
        count = await vector_store.count()
        return {"status": "healthy", "indexed_documents": count, "version": "1.0.0"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}

