from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class UserProfile(SQLModel, table=True):
    """
    User service owns profile data.
    user_id is a foreign key to the Auth service's users table
    (enforced only logically – different DBs).
    """
    __tablename__ = "user_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(unique=True, index=True)   # matches auth service user.id
    bio: Optional[str] = Field(default=None, max_length=500)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

