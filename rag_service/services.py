"""RAG Service business logic."""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import settings
from .rag_engine import rag_engine
from .vector_store import vector_store

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


class RecommendationService:
    """Personalized recommendations."""

    @staticmethod
    async def get_recommendations(
        user_history: List[str],
        top_k: int = 10,
        diversify: bool = True,
    ) -> Dict[str, Any]:
        if not user_history:
            return {
                "based_on": [],
                "recommendations": [],
                "message": "No reading history provided",
            }

        all_results = []
        for work_id in user_history[:5]:
            all_results.extend(await rag_engine.recommend_similar(work_id, top_k=3))

        seen = set(user_history)
        unique_results = []
        for result in all_results:
            work_id = result.get("work_id")
            if work_id and work_id not in seen:
                seen.add(work_id)
                unique_results.append(result)

        unique_results.sort(key=lambda item: item.get("score", 0), reverse=True)

        if diversify:
            unique_results = RecommendationService._diversify_results(unique_results, top_k)

        return {
            "based_on": user_history,
            "recommendations": unique_results[:top_k],
            "count": len(unique_results[:top_k]),
        }

    @staticmethod
    def _diversify_results(results: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        if not results:
            return results

        genre_counts: Dict[str, int] = {}
        diversified = []

        for result in results:
            genres = result.get("genres") or ["Unknown"]
            primary_genre = genres[0] if genres else "Unknown"
            if genre_counts.get(primary_genre, 0) < 2:
                diversified.append(result)
                genre_counts[primary_genre] = genre_counts.get(primary_genre, 0) + 1
            if len(diversified) >= top_k:
                break

        if len(diversified) < top_k:
            for result in results:
                if result not in diversified:
                    diversified.append(result)
                if len(diversified) >= top_k:
                    break

        return diversified


class IndexingService:
    """Content indexing operations."""

    @staticmethod
    async def index_book_profile(book: Dict[str, Any]) -> bool:
        return await rag_engine.index_book(book)

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
            "last_updated": datetime.utcnow().isoformat(),
        }

