"""
API Router - Compatible with Old V3 + New Rich Profiles
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Optional
import logging
import aiohttp
import asyncio

from services.enrichment import enrichment_service
from database import db
from utils.helpers import slugify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3", tags=["books"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "book-service-v4",
        "message": "On-demand enrichment with MongoDB"
    }


# ====================== BOOKS ======================
@router.get("/books/search")
async def search_books(
    q: str = Query(..., min_length=1, description="Book title or keywords"),
    limit: int = 10,
    force_refresh: bool = False
):
    """Old endpoint: /api/v3/books/search?q=..."""
    
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    try:
        # Check cache first
        work_id = slugify(q)
        if not force_refresh:
            cached = await db.get_book(work_id)
            if cached:
                return {"results": [cached], "total": 1, "from_cache": True}

        # Enrich on demand
        profile = await enrichment_service.enrich_book(q)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Book not found: {q}")

        return {
            "results": [profile.model_dump()],
            "total": 1,
            "query": q
        }
    
    except HTTPException:
        raise
    
    except aiohttp.ClientError as e:
        logger.error(f"External API error for book '{q}': {e}")
        raise HTTPException(status_code=503, detail="External APIs are temporarily unavailable")
    
    except asyncio.TimeoutError:
        logger.error(f"Timeout searching book '{q}'")
        raise HTTPException(status_code=504, detail="Book enrichment timed out")
    
    except Exception as e:
        logger.exception(f"Book search error for '{q}'")
        raise HTTPException(status_code=500, detail="Internal enrichment error")


# ====================== AUTHORS ======================
@router.get("/authors/search")
async def search_authors(
    name: str = Query(..., min_length=1, description="Author name"),
    force_refresh: bool = False
):
    """Old endpoint: /api/v3/authors/search?name=..."""
    
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Author name cannot be empty")
    
    try:
        if not force_refresh:
            cached = await db.get_author(slugify(name))
            if cached:
                return {"results": [cached], "total": 1, "from_cache": True}

        profile = await enrichment_service.enrich_author(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Author not found: {name}")

        return {
            "results": [profile.model_dump()],
            "total": 1,
            "query": name
        }
    
    except HTTPException:
        raise
    
    except aiohttp.ClientError as e:
        logger.error(f"External API error for author '{name}': {e}")
        raise HTTPException(status_code=503, detail="External APIs are temporarily unavailable")
    
    except asyncio.TimeoutError:
        logger.error(f"Timeout searching author '{name}'")
        raise HTTPException(status_code=504, detail="Author enrichment timed out")
    
    except Exception as e:
        logger.exception(f"Author search error for '{name}'")
        raise HTTPException(status_code=500, detail="Internal enrichment error")


@router.get("/authors/{author_id}/books")
async def get_author_books(
    author_id: str,
    limit: int = Query(50, description="Maximum number of books to return"),
    offset: int = Query(0, description="Number of books to skip"),
    force_refresh: bool = False
):
    """Get all books by an author"""
    
    try:
        # Get author profile
        if not force_refresh:
            author_data = await db.get_author(author_id)
            if author_data and "books" in author_data and author_data["books"]:
                books = author_data["books"][offset:offset+limit]
                return {
                    "author": author_data.get("name", author_id),
                    "author_id": author_id,
                    "books": books,
                    "total": len(author_data["books"]),
                    "returned": len(books),
                    "from_cache": True
                }

        # Need to enrich author to get books
        author_name = author_id.replace("-", " ").title()  # Convert slug back to name
        profile = await enrichment_service.enrich_author(author_name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Author not found: {author_id}")

        books = profile.books[offset:offset+limit]
        return {
            "author": profile.name,
            "author_id": author_id,
            "books": [book.model_dump() for book in books],
            "total": len(profile.books),
            "returned": len(books),
            "from_cache": False
        }
    
    except HTTPException:
        raise
    
    except aiohttp.ClientError as e:
        logger.error(f"External API error for author books '{author_id}': {e}")
        raise HTTPException(status_code=503, detail="External APIs are temporarily unavailable")
    
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching author books '{author_id}'")
        raise HTTPException(status_code=504, detail="Author books fetch timed out")
    
    except Exception as e:
        logger.exception(f"Author books error for '{author_id}'")
        raise HTTPException(status_code=500, detail="Internal server error")


# ====================== SERIES ======================
@router.get("/series/search")
async def search_series(
    name: str = Query(..., min_length=1, description="Series name"),
    force_refresh: bool = False
):
    """New + Old compatible Series endpoint"""
    
    # Input validation
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Series name cannot be empty")
    
    try:
        if not force_refresh:
            series_id = slugify(name)
            cached = await db.get_series(series_id)
            if cached:
                return {"results": [cached], "total": 1, "from_cache": True}

        # Attempt enrichment with new Wikipedia-first strategy
        profile = await enrichment_service.enrich_series(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Series not found: {name}")

        return {
            "results": [profile.model_dump()],
            "total": 1,
            "query": name
        }
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    
    except aiohttp.ClientError as e:
        logger.error(f"External API error enriching series '{name}': {e}")
        raise HTTPException(
            status_code=503, 
            detail="Enrichment service temporarily unavailable. External APIs are unreachable."
        )
    
    except asyncio.TimeoutError:
        logger.error(f"Timeout enriching series '{name}'")
        raise HTTPException(
            status_code=504, 
            detail="Series enrichment timed out. Please try again."
        )
    
    except Exception as e:
        logger.exception(f"Unexpected error enriching series: {name}")
        raise HTTPException(
            status_code=500, 
            detail="Internal server error during enrichment. Please contact support."
        )


# ====================== UNIFIED SEARCH ======================
@router.post("/search")
async def unified_search(payload: Dict):
    """Old unified endpoint support"""
    query = payload.get("query")
    search_type = payload.get("type", "book").lower()

    try:
        if search_type == "author":
            result = await enrichment_service.enrich_author(query)
            return {"type": "author", "results": [result.model_dump()] if result else []}

        elif search_type == "series":
            result = await enrichment_service.enrich_series(query)
            return {"type": "series", "results": [result.model_dump()] if result else []}

        else:  # book by default
            result = await enrichment_service.enrich_book(query)
            return {"type": "book", "results": [result.model_dump()] if result else []}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))