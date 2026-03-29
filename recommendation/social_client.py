"""Graceful social-signal client fallback for recommendation ranking."""

from typing import Dict, Iterable, Optional


async def get_social_signals(book_ids: Iterable[str], user_id: Optional[str] = None) -> Dict[str, dict]:
    # Keep recommendation endpoint functional even when social integration is unavailable.
    return {str(book_id): {} for book_id in book_ids if book_id}


async def get_user_profile(user_id: str) -> dict:
    # No-op fallback; personalized vector can be wired later from social/user profile data.
    return {}

