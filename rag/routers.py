"""FastAPI routers for RAG Service."""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .services import IndexingService, SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag")


class BookSyncRequest(BaseModel):
    work_id: str = Field(..., min_length=1)


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



@router.get("/stats")
async def get_stats():
    try:
        return await IndexingService.get_stats()
    except Exception as exc:
        logger.error("Stats failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync/books")
async def sync_books(limit: int = Query(50, ge=1, le=500), skip: int = Query(0, ge=0)):
    try:
        return await IndexingService.sync_books_from_book_v3(limit=limit, skip=skip)
    except Exception as exc:
        logger.error("Book sync failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync/books/by-work-id")
async def sync_book_by_work_id(request: BookSyncRequest):
    try:
        result = await IndexingService.sync_book_by_work_id(request.work_id)
        if not result.get("indexed") and result.get("reason") == "not_found":
            raise HTTPException(status_code=404, detail="Book not found in Book Service V3")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Book sync by work_id failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def health_check():
    from rag import vector_store

    try:
        count = await vector_store.count()
        return {"status": "healthy", "indexed_documents": count, "version": "1.0.0"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}

