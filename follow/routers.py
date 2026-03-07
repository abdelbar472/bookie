import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .auth import get_current_user_id
from .schemas import FollowResponse, FollowStats, FollowListResponse
from .services import (
    follow_user,
    unfollow_user,
    is_following,
    get_followers,
    get_following,
    get_follow_stats,
)

router = APIRouter(prefix="/follow", tags=["follow"])
logger = logging.getLogger(__name__)


# ── follow ─────────────────────────────────────────────────────────────────────

@router.post("/{followee_id}", response_model=FollowResponse, status_code=status.HTTP_201_CREATED)
async def follow(
    followee_id: int,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Follow a user by their user_id. Requires a valid Bearer token."""
    try:
        follow_obj = await follow_user(session, current_user_id, followee_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return FollowResponse(
        follower_id=follow_obj.follower_id,
        followee_id=follow_obj.followee_id,
        created_at=follow_obj.created_at,
    )


@router.delete("/{followee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow(
    followee_id: int,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Unfollow a user by their user_id."""
    try:
        await unfollow_user(session, current_user_id, followee_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/check/{followee_id}")
async def check_follow(
    followee_id: int,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Check whether the current user follows *followee_id*."""
    result = await is_following(session, current_user_id, followee_id)
    return {"following": result, "follower_id": current_user_id, "followee_id": followee_id}


# ── lists ──────────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/followers", response_model=FollowListResponse)
async def list_followers(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Paginated list of followers for *user_id*."""
    items, total = await get_followers(session, user_id, skip=skip, limit=limit)
    return FollowListResponse(items=items, total=total)


@router.get("/users/{user_id}/following", response_model=FollowListResponse)
async def list_following(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Paginated list of users that *user_id* follows."""
    items, total = await get_following(session, user_id, skip=skip, limit=limit)
    return FollowListResponse(items=items, total=total)


@router.get("/users/{user_id}/stats", response_model=FollowStats)
async def follow_stats(
    user_id: int,
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Follower / following counts for *user_id*."""
    stats = await get_follow_stats(session, user_id)
    return FollowStats(**stats)
