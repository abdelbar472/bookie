import logging
from typing import List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from .models import Follow
from .schemas import FollowerEntry

logger = logging.getLogger(__name__)


async def follow_user(
    session: AsyncSession,
    follower_id: int,
    followee_id: int,
) -> Follow:
    """Create a follow relationship. Raises ValueError on self-follow or duplicate."""
    if follower_id == followee_id:
        raise ValueError("A user cannot follow themselves.")

    # check duplicate
    existing = await session.execute(
        select(Follow).where(
            Follow.follower_id == follower_id,
            Follow.followee_id == followee_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Already following this user.")

    follow = Follow(follower_id=follower_id, followee_id=followee_id)
    session.add(follow)
    await session.commit()
    await session.refresh(follow)
    logger.info("user %s now follows user %s", follower_id, followee_id)
    return follow


async def unfollow_user(
    session: AsyncSession,
    follower_id: int,
    followee_id: int,
) -> None:
    """Delete a follow relationship. Raises ValueError if it doesn't exist."""
    result = await session.execute(
        select(Follow).where(
            Follow.follower_id == follower_id,
            Follow.followee_id == followee_id,
        )
    )
    follow = result.scalar_one_or_none()
    if follow is None:
        raise ValueError("Not following this user.")

    await session.delete(follow)
    await session.commit()
    logger.info("user %s unfollowed user %s", follower_id, followee_id)


async def is_following(
    session: AsyncSession,
    follower_id: int,
    followee_id: int,
) -> bool:
    result = await session.execute(
        select(Follow).where(
            Follow.follower_id == follower_id,
            Follow.followee_id == followee_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def get_followers(
    session: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[FollowerEntry], int]:
    """Return a page of followers for *user_id* plus total count."""
    count_result = await session.execute(
        select(func.count()).where(Follow.followee_id == user_id)
    )
    total = count_result.scalar_one()

    rows = await session.execute(
        select(Follow)
        .where(Follow.followee_id == user_id)
        .order_by(Follow.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    entries = [
        FollowerEntry(user_id=row.follower_id, created_at=row.created_at)
        for row in rows.scalars()
    ]
    return entries, total


async def get_following(
    session: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[FollowerEntry], int]:
    """Return a page of users that *user_id* follows, plus total count."""
    count_result = await session.execute(
        select(func.count()).where(Follow.follower_id == user_id)
    )
    total = count_result.scalar_one()

    rows = await session.execute(
        select(Follow)
        .where(Follow.follower_id == user_id)
        .order_by(Follow.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    entries = [
        FollowerEntry(user_id=row.followee_id, created_at=row.created_at)
        for row in rows.scalars()
    ]
    return entries, total


async def get_follow_stats(
    session: AsyncSession,
    user_id: int,
) -> dict:
    followers_count = (
        await session.execute(
            select(func.count()).where(Follow.followee_id == user_id)
        )
    ).scalar_one()

    following_count = (
        await session.execute(
            select(func.count()).where(Follow.follower_id == user_id)
        )
    ).scalar_one()

    return {
        "user_id": user_id,
        "followers_count": followers_count,
        "following_count": following_count,
    }


