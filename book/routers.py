"""
FastAPI routers for Book Service V3
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import List
import logging

from .schemas import BookSearchResponse, HealthResponse, BookProfile
from .services import BookService, HealthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3")


# ==================== BOOK ENDPOINTS ====================

@router.get("/books/search", response_model=BookSearchResponse)
async def search_books(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    skip_cache: bool = Query(False, description="Skip cache and fetch fresh data")
):
    """
    Search for books with enrichment
    """
    try:
        result = await BookService.search_books(q, limit, skip_cache)
        return result
    except Exception as e:
        logger.error(f"Book search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/books/{work_id}", response_model=BookProfile)
async def get_book(work_id: str):
    """
    Get specific book by work ID
    """
    book = await BookService.get_book_by_id(work_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book not found: {work_id}"
        )
    return book


@router.get("/books", response_model=List[BookProfile])
async def list_books(
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0)
):
    """
    List all cached books
    """
    try:
        return await BookService.list_books(limit, skip)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== HEALTH ====================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Service health check
    """
    return await HealthService.get_health()