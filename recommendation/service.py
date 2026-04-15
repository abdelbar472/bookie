"""Recommendation business logic using rag_service gRPC retrieval."""

from typing import Any, Dict, List

from .grpc_client import get_similar_books
from .profile import UserProfileBuilder, apply_interaction, get_profile_history
from .ranking import diversify_by_genre, rank_unique_recommendations


class RecommendationService:
    @staticmethod
    async def _fetch_similar(work_id: str, top_k: int = 3) -> List[Dict[str, Any]]:
        try:
            return await get_similar_books(work_id, top_k=top_k)
        except Exception:
            return []

    @staticmethod
    async def get_recommendations(
        user_id: str,
        history_book_ids: List[str],
        top_k: int = 10,
        diversify: bool = True,
        current_book_id: str = "",
    ) -> Dict[str, Any]:
        history = list(dict.fromkeys(history_book_ids))

        if not history and user_id:
            history = get_profile_history(user_id, limit=50)

        if current_book_id and current_book_id not in history:
            history.insert(0, current_book_id)

        if not history:
            return {
                "based_on": [],
                "profile": {"history_size": 0, "seed_work_ids": []},
                "recommendations": [],
                "message": "No reading history provided",
                "source": "recommendation-service",
            }

        profile = UserProfileBuilder.from_history(history)
        seeds = profile["seed_work_ids"][:5]

        all_results: List[Dict[str, Any]] = []
        for work_id in seeds:
            all_results.extend(await RecommendationService._fetch_similar(work_id, top_k=3))

        ranked = rank_unique_recommendations(all_results, history)
        if diversify:
            ranked = diversify_by_genre(ranked, top_k)

        return {
            "based_on": history,
            "profile": profile,
            "recommendations": ranked[:top_k],
            "count": len(ranked[:top_k]),
            "source": "recommendation-service",
        }

    @staticmethod
    async def update_user_profile(user_id: str, book_id: str, interaction_type: str, value: float) -> Dict[str, Any]:
        apply_interaction(user_id=user_id, book_id=book_id, interaction_type=interaction_type, value=value)
        history = get_profile_history(user_id=user_id, limit=10)
        return {
            "success": True,
            "user_id": user_id,
            "history_size": len(history),
            "seed_work_ids": history,
        }
