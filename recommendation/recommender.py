import logging
from typing import Optional, List, Dict

from .config import settings
from .vector_store import search_recommendations, _client, point_id_from_book_id
from .embedder import generate_query_embedding
from .social_client import get_social_signals, get_user_profile

logger = logging.getLogger(__name__)


async def generate_recommendations(
        user_id: Optional[str] = None,
        query: Optional[str] = None,
        current_book_id: Optional[str] = None,
        exclude_read: bool = True,
        limit: int = 10
) -> Dict:
    """Main recommendation pipeline"""

    # Build query vectors
    content_vector = None
    author_style_vector = None
    user_vector = None

    if query:
        content_vector = generate_query_embedding(query)
        author_style_vector = content_vector

    if current_book_id:
        # Get vectors of reference book
        if _client is not None:
            book_vectors = await _client.retrieve(
                collection_name=settings.QDRANT_COLLECTION,
                ids=[point_id_from_book_id(current_book_id)],
                with_vectors=True
            )
            if book_vectors:
                content_vector = book_vectors[0].vector.get("content")
                author_style_vector = book_vectors[0].vector.get("author_style")

    if user_id:
        # Get user preference vector
        user_profile = await get_user_profile(user_id)
        if user_profile and user_profile.get("preference_vector"):
            user_vector = user_profile["preference_vector"]

    # Search candidates
    candidates = await search_recommendations(
        content_vector=content_vector,
        author_style_vector=author_style_vector,
        user_vector=user_vector,
        limit=50
    )

    # Fetch social signals for re-ranking
    book_ids = [c["id"] for c in candidates]
    social_signals = await get_social_signals(book_ids, user_id) if user_id else {}

    # Re-rank with hybrid scoring
    ranked = await _rank_candidates(candidates, social_signals, user_id)

    return {
        "user_id": user_id,
        "recommendations": ranked[:limit],
        "total_candidates": len(candidates)
    }


async def _rank_candidates(
        candidates: List[dict],
        social_signals: Dict,
        user_id: Optional[str]
) -> List[dict]:
    """Re-rank using weighted scoring"""
    scored = []

    for cand in candidates:
        payload = cand["payload"]
        base_score = cand["score"]

        # Component scores
        content_score = base_score
        author_score = 0.0
        social_score = 0.0

        # Social boost
        social = social_signals.get(cand["id"], {})
        if social:
            social_score = (
                    min(social.get("likes", 0) / 100, 1.0) * 0.05 +
                    min(social.get("shelves", 0) / 50, 1.0) * 0.03 +
                    (social.get("avg_rating", 0) / 5.0) * 0.02
            )
            if social.get("friends_shelved"):
                social_score += len(social["friends_shelved"]) * 0.05

        # Calculate final score
        final_score = (
                content_score * settings.WEIGHT_CONTENT +
                author_score * settings.WEIGHT_AUTHOR_STYLE +
                social_score * settings.WEIGHT_SOCIAL
        )

        scored.append({
            "book_id": cand["id"],
            "title": payload.get("title"),
            "authors": payload.get("authors", []),
            "thumbnail": payload.get("thumbnail"),
            "score": round(final_score, 4),
            "reason": _generate_reason(social, payload)
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _generate_reason(social: dict, payload: dict) -> str:
    """Generate human-readable recommendation reason"""
    reasons = []

    if social.get("friends_shelved"):
        reasons.append(f"{len(social['friends_shelved'])} friends added this")
    if social.get("avg_rating", 0) > 4.0:
        reasons.append("Highly rated")
    if not reasons:
        reasons.append("Based on your reading history")

    return "; ".join(reasons)