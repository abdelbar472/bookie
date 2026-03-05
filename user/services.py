from datetime import datetime
from typing import Optional
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .models import UserProfile

logger = logging.getLogger(__name__)


async def get_or_create_profile(session: AsyncSession, user_id: int) -> UserProfile:
    """Get existing profile or create an empty one for the user."""
    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        logger.info("Created new profile for user_id=%s", user_id)
    return profile


async def update_profile(
    session: AsyncSession,
    user_id: int,
    bio: Optional[str],
    avatar_url: Optional[str],
) -> UserProfile:
    profile = await get_or_create_profile(session, user_id)
    if bio is not None:
        profile.bio = bio
    if avatar_url is not None:
        profile.avatar_url = avatar_url
    profile.updated_at = datetime.utcnow()
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile

