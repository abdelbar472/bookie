"""HTTP routes for recommendation microservice."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .service import RecommendationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


class RecommendationRequestBody(BaseModel):
    user_id: str = Field(default="")
    history_book_ids: List[str] = Field(default_factory=list)
    current_book_id: str = Field(default="")


class InteractionEventBody(BaseModel):
    user_id: str
    book_id: str
    interaction_type: str
    value: float = 1.0


@router.post("/recommend")
async def recommend(
    payload: RecommendationRequestBody,
    top_k: int = Query(10, ge=1, le=50),
    diversify: bool = Query(True),
):
    try:
        return await RecommendationService.get_recommendations(
            user_id=payload.user_id,
            history_book_ids=payload.history_book_ids,
            top_k=top_k,
            diversify=diversify,
            current_book_id=payload.current_book_id,
        )
    except Exception as exc:
        logger.error("Recommendation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/profile/events")
async def update_profile_event(payload: InteractionEventBody):
    try:
        return await RecommendationService.update_user_profile(
            user_id=payload.user_id,
            book_id=payload.book_id,
            interaction_type=payload.interaction_type,
            value=payload.value,
        )
    except Exception as exc:
        logger.error("Profile update failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "recommendation"}
