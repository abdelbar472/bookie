from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class UserPayload(BaseModel):
    """User data received from Auth service via gRPC"""
    id: int
    username: str
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool


class ProfileResponse(BaseModel):
    """Combined response: auth data + local profile data"""
    id: int
    username: str
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

