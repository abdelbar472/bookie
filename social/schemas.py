from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LikeResponse(BaseModel):
    isbn: str
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RatingUpsertRequest(BaseModel):
    rating: float = Field(ge=0.5, le=5.0, multiple_of=0.5)


class RatingResponse(BaseModel):
    isbn: str
    user_id: int
    rating: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewCreateRequest(BaseModel):
    isbn: str = Field(min_length=3, max_length=20)
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=10, max_length=4000)


class ReviewReplyCreateRequest(BaseModel):
    title: str = Field(default="Reply", min_length=3, max_length=200)
    content: str = Field(min_length=2, max_length=4000)


class ReviewUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    content: str | None = Field(default=None, min_length=2, max_length=4000)


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    isbn: str
    parent_review_id: int | None = None
    title: str
    content: str
    likes_count: int = 0
    replies_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int


class ReviewLikeResponse(BaseModel):
    review_id: int
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ShelfCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    visibility: Literal["private", "public"] = "private"


class ShelfUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    visibility: Literal["private", "public"] | None = None


class ShelfResponse(BaseModel):
    id: int
    user_id: int
    name: str
    visibility: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShelfItemCreateRequest(BaseModel):
    isbn: str = Field(min_length=3, max_length=20)
    position: int = Field(default=1, ge=1)


class ShelfItemResponse(BaseModel):
    id: int
    shelf_id: int
    isbn: str
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ShelfItemListResponse(BaseModel):
    items: list[ShelfItemResponse]
    total: int


class BookSocialStatsResponse(BaseModel):
    isbn: str
    likes_count: int
    ratings_count: int
    avg_rating: float | None

