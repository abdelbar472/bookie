from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field, UniqueConstraint


class Follow(SQLModel, table=True):
    """
    Represents a follower → followee relationship.
    Both IDs reference user_id values from the Auth service.
    """

    __tablename__ = "follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id", name="uq_follow_pair"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    follower_id: int = Field(index=True)   # the user who follows
    followee_id: int = Field(index=True)   # the user being followed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


