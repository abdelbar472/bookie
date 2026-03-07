from pydantic import BaseModel
from datetime import datetime
from typing import List


class FollowResponse(BaseModel):
    """Returned after a successful follow/unfollow action."""
    follower_id: int
    followee_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowStats(BaseModel):
    """Follower / following counts for a user."""
    user_id: int
    followers_count: int
    following_count: int


class FollowerEntry(BaseModel):
    """One entry in a followers / following list."""
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowListResponse(BaseModel):
    items: List[FollowerEntry]
    total: int

