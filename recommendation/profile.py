"""User profile helpers for recommendation service."""

from collections import defaultdict
from typing import Dict, List, TypedDict


class UserProfile(TypedDict):
    history_size: int
    seed_work_ids: List[str]


class UserProfileBuilder:
    @staticmethod
    def from_history(user_history: List[str]) -> UserProfile:
        return {
            "history_size": len(user_history),
            "seed_work_ids": list(dict.fromkeys(user_history)),
        }


# In-memory profile signals: user_id -> {book_id -> weight}
_PROFILE_SIGNALS: Dict[str, Dict[str, float]] = defaultdict(dict)


def apply_interaction(user_id: str, book_id: str, interaction_type: str, value: float) -> None:
    if not user_id or not book_id:
        return

    base = {
        "like": 1.0,
        "rating": max(0.2, min(1.0, value / 5.0 if value else 0.2)),
        "review": 1.2,
        "shelf_add": 0.6,
    }.get(interaction_type, 0.4)

    bucket = _PROFILE_SIGNALS[user_id]
    bucket[book_id] = bucket.get(book_id, 0.0) + float(base)


def get_profile_history(user_id: str, limit: int = 50) -> List[str]:
    bucket = _PROFILE_SIGNALS.get(user_id, {})
    if not bucket:
        return []

    ranked = sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)
    return [book_id for book_id, _ in ranked[:limit]]
