"""
FastAPI routers for Book Service V3
"""
from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
import logging

from .schemas import (
    SearchRequest, BookSearchResponse, AuthorSearchResponse,
    SeriesSearchResponse, HealthResponse, BookProfile
)
from .services import BookService, AuthorService, SeriesService, HealthService
from .database import DatabaseUnavailableError

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
    Search for books with rich enrichment
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


# ==================== AUTHOR ENDPOINTS ====================

@router.get("/authors/search", response_model=AuthorSearchResponse)
async def search_authors(
    name: str = Query(..., min_length=1, max_length=100, description="Author name")
):
    """
    Search for author and their complete bibliography
    """
    try:
        result = await AuthorService.search_author(name)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Author not found: {name}"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Author search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/authors/{author_id}")
async def get_author(author_id: str):
    """
    Get author by ID
    """
    author = await AuthorService.get_author_by_id(author_id)
    if not author:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Author not found: {author_id}"
        )
    return author


# ==================== SERIES ENDPOINTS ====================

@router.get("/series/search", response_model=SeriesSearchResponse)
async def search_series(
    name: str = Query(..., min_length=1, max_length=100, description="Series name")
):
    """
    Search for book series with reading order
    """
    try:
        result = await SeriesService.search_series(name)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Series not found: {name}"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Series search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/series/{series_id}")
async def get_series(series_id: str):
    """
    Get series by ID
    """
    series = await SeriesService.get_series_by_id(series_id)
    if not series:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Series not found: {series_id}"
        )
    return series


# ==================== UNIFIED SEARCH ====================

@router.post("/search")
async def unified_search(request: SearchRequest):
    """
    Unified search endpoint for books, authors, or series
    """
    try:
        if request.type == "book":
            return await BookService.search_books(request.query, request.limit, request.skip_cache)
        elif request.type == "author":
            result = await AuthorService.search_author(request.query)
            if not result:
                raise HTTPException(status_code=404, detail="Author not found")
            return result
        elif request.type == "series":
            result = await SeriesService.search_series(request.query)
            if not result:
                raise HTTPException(status_code=404, detail="Series not found")
            return result
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Type must be 'book', 'author', or 'series'"
            )
    except HTTPException:
        raise
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