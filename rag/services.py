"""RAG Service business logic."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import settings
from .grpc_client import book_service_client
from rag.engine import rag_engine
from rag.vector_store import vector_store

logger = logging.getLogger(__name__)


class SearchService:
    """Search operations."""

    @staticmethod
    async def semantic_search(
        query: str,
        top_k: int = 5,
        entity_type: Optional[str] = None,
        genre: Optional[str] = None,
        author: Optional[str] = None,
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}
        if genre:
            filters["genres"] = [genre]
        if author:
            filters["author"] = author

        results = await rag_engine.search(
            query=query,
            top_k=top_k,
            entity_type=entity_type,
            filters=filters if filters else None,
        )
        return {
            "query": query,
            "results_count": len(results),
            "results": results,
            "filters_applied": {
                "entity_type": entity_type,
                "genre": genre,
                "author": author,
            },
        }

    @staticmethod
    async def find_similar_books(work_id: str, top_k: int = 5) -> Dict[str, Any]:
        results = await rag_engine.recommend_similar(work_id, top_k)
        return {
            "reference_work_id": work_id,
            "similar_books": results,
            "count": len(results),
        }

    @staticmethod
    async def thematic_search(themes: List[str], top_k: int = 10) -> Dict[str, Any]:
        query = " ".join(themes)
        results = await rag_engine.search(query=query, top_k=top_k, entity_type="book")

        filtered = []
        query_themes = {t.lower() for t in themes}
        for result in results:
            result_themes = {t.lower() for t in result.get("themes", [])}
            if query_themes & result_themes:
                filtered.append(result)

        return {"themes": themes, "results": filtered, "count": len(filtered)}



class IndexingService:
    """Content indexing operations."""

    @staticmethod
    async def index_book_profile(book: Dict[str, Any]) -> bool:
        return await rag_engine.index_book(book)

    @staticmethod
    def _map_book_v3_payload(book_msg: Any) -> Dict[str, Any]:
        return {
            "work_id": book_msg.work_id,
            "title": book_msg.title,
            "primary_author": book_msg.primary_author,
            "authors": list(book_msg.authors),
            "description": book_msg.description,
            "genres": list(book_msg.genres),
            "rag_document": book_msg.rag_document,
            "content_analysis": {
                "key_themes": list(book_msg.themes),
            },
        }

    @staticmethod
    async def sync_book_by_work_id(work_id: str) -> Dict[str, Any]:
        book = await book_service_client.get_book(work_id)
        if not book:
            return {"indexed": False, "work_id": work_id, "reason": "not_found"}

        mapped = IndexingService._map_book_v3_payload(book)
        indexed = await rag_engine.index_book(mapped)
        return {"indexed": indexed, "work_id": work_id}

    @staticmethod
    async def sync_books_from_book_v3(limit: int = 50, skip: int = 0) -> Dict[str, int]:
        books = await book_service_client.list_books(limit=limit, skip=skip)
        stats = {"requested": limit, "received": len(books), "indexed": 0, "failed": 0}

        for book in books:
            mapped = IndexingService._map_book_v3_payload(book)
            if await rag_engine.index_book(mapped):
                stats["indexed"] += 1
            else:
                stats["failed"] += 1

        return stats

    @staticmethod
    async def index_author_profile(author: Dict[str, Any]) -> bool:
        return await rag_engine.index_author(author)

    @staticmethod
    async def batch_index(books: List[Dict[str, Any]]) -> Dict[str, int]:
        stats = {"books": 0, "failed": 0}
        for book in books:
            if await rag_engine.index_book(book):
                stats["books"] += 1
            else:
                stats["failed"] += 1
        return stats

    @staticmethod
    async def get_stats() -> Dict[str, Any]:
        count = await vector_store.count()
        return {
            "total_indexed": count,
            "collection": settings.QDRANT_COLLECTION_NAME,
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

