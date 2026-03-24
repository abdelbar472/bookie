from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user_id
from .book_grpc_client import assert_book_exists, get_book_details
from .database import get_session
from .rag_grpc_client import track_interaction
from .schemas import (
    BookSocialStatsResponse,
    LikeResponse,
    RatingResponse,
    RatingUpsertRequest,
    ReviewCreateRequest,
    ReviewLikeResponse,
    ReviewListResponse,
    ReviewReplyCreateRequest,
    ReviewResponse,
    ReviewUpdateRequest,
    ShelfCreateRequest,
    ShelfItemCreateRequest,
    ShelfBookItemResponse,
    ShelfBookListResponse,
    ShelfItemListResponse,
    ShelfItemResponse,
    ShelfResponse,
    ShelfUpdateRequest,
)
from .services import (
    add_shelf_item,
    create_review,
    create_review_reply,
    create_shelf,
    delete_review,
    delete_shelf,
    get_book_social_stats,
    get_my_rating,
    get_review_metrics,
    like_book,
    like_review,
    list_book_reviews,
    list_my_shelves,
    list_review_replies,
    list_shelf_items,
    remove_shelf_item,
    unlike_book,
    unlike_review,
    update_review,
    update_shelf,
    upsert_rating,
)

router = APIRouter(prefix="/social", tags=["social"])


def _review_payload(items, metrics: dict[int, dict[str, int]]) -> list[ReviewResponse]:
    payload: list[ReviewResponse] = []
    for item in items:
        counters = metrics.get(item.id or -1, {"likes_count": 0, "replies_count": 0})
        payload.append(
            ReviewResponse(
                id=item.id,
                user_id=item.user_id,
                isbn=item.isbn,
                parent_review_id=item.parent_review_id,
                title=item.title,
                content=item.content,
                likes_count=counters["likes_count"],
                replies_count=counters["replies_count"],
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return payload


@router.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "social-service"}


@router.post("/likes/{isbn}", response_model=LikeResponse, status_code=status.HTTP_201_CREATED)
async def like_book_route(
    isbn: str,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        await assert_book_exists(isbn)
        row = await like_book(session, current_user_id, isbn)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=code, detail=detail)

    await track_interaction(
        user_id=current_user_id,
        book_id=isbn,
        qdrant_id=isbn,
        interaction_type="like",
        value=1.0,
    )

    return row


@router.delete("/likes/{isbn}", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_book_route(
    isbn: str,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    removed = await unlike_book(session, current_user_id, isbn)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Like not found")


@router.put("/ratings/{isbn}", response_model=RatingResponse)
async def upsert_rating_route(
    isbn: str,
    payload: RatingUpsertRequest,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        await assert_book_exists(isbn)
        row = await upsert_rating(session, current_user_id, isbn, payload.rating)
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=code, detail=detail)

    await track_interaction(
        user_id=current_user_id,
        book_id=isbn,
        qdrant_id=isbn,
        interaction_type="rating",
        value=float(payload.rating),
    )
    return row


@router.get("/ratings/{isbn}/me", response_model=RatingResponse)
async def get_my_rating_route(
    isbn: str,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    row = await get_my_rating(session, current_user_id, isbn)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rating not found")
    return row


@router.get("/books/{isbn}/stats", response_model=BookSocialStatsResponse)
async def get_book_stats_route(
    isbn: str,
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    return await get_book_social_stats(session, isbn)


@router.post("/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review_route(
    payload: ReviewCreateRequest,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        await assert_book_exists(payload.isbn)
        row = await create_review(
            session,
            current_user_id,
            payload.isbn,
            payload.title,
            payload.content,
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=code, detail=detail)

    await track_interaction(
        user_id=current_user_id,
        book_id=payload.isbn,
        qdrant_id=payload.isbn,
        interaction_type="review",
        value=1.0,
    )

    return ReviewResponse(
        id=row.id,
        user_id=row.user_id,
        isbn=row.isbn,
        parent_review_id=row.parent_review_id,
        title=row.title,
        content=row.content,
        likes_count=0,
        replies_count=0,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/reviews/{review_id}/replies", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review_reply_route(
    review_id: int,
    payload: ReviewReplyCreateRequest,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        row = await create_review_reply(
            session,
            current_user_id,
            review_id,
            payload.title,
            payload.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return ReviewResponse(
        id=row.id,
        user_id=row.user_id,
        isbn=row.isbn,
        parent_review_id=row.parent_review_id,
        title=row.title,
        content=row.content,
        likes_count=0,
        replies_count=0,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.patch("/reviews/{review_id}", response_model=ReviewResponse)
async def update_review_route(
    review_id: int,
    payload: ReviewUpdateRequest,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    if payload.title is None and payload.content is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update fields provided")

    try:
        row = await update_review(
            session,
            current_user_id,
            review_id,
            payload.title,
            payload.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    metrics = await get_review_metrics(session, [row.id])
    return _review_payload([row], metrics)[0]


@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review_route(
    review_id: int,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        await delete_review(session, current_user_id, review_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post("/reviews/{review_id}/likes", response_model=ReviewLikeResponse, status_code=status.HTTP_201_CREATED)
async def like_review_route(
    review_id: int,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        row = await like_review(session, current_user_id, review_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return row


@router.delete("/reviews/{review_id}/likes", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_review_route(
    review_id: int,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    removed = await unlike_review(session, current_user_id, review_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review like not found")


@router.get("/books/{isbn}/reviews", response_model=ReviewListResponse)
async def list_reviews_route(
    isbn: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    items, total = await list_book_reviews(session, isbn, skip=skip, limit=limit)
    metrics = await get_review_metrics(session, [item.id for item in items if item.id is not None])
    return ReviewListResponse(items=_review_payload(items, metrics), total=total)


@router.get("/reviews/{review_id}/replies", response_model=ReviewListResponse)
async def list_review_replies_route(
    review_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        items, total = await list_review_replies(session, review_id, skip=skip, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    metrics = await get_review_metrics(session, [item.id for item in items if item.id is not None])
    return ReviewListResponse(items=_review_payload(items, metrics), total=total)


@router.post("/shelves", response_model=ShelfResponse, status_code=status.HTTP_201_CREATED)
async def create_shelf_route(
    payload: ShelfCreateRequest,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await create_shelf(session, current_user_id, payload.name, payload.visibility)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/shelves/me", response_model=list[ShelfResponse])
async def list_my_shelves_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    items, _ = await list_my_shelves(session, current_user_id, skip=skip, limit=limit)
    return items


@router.patch("/shelves/{shelf_id}", response_model=ShelfResponse)
async def update_shelf_route(
    shelf_id: int,
    payload: ShelfUpdateRequest,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    if payload.name is None and payload.visibility is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update fields provided")

    try:
        return await update_shelf(
            session,
            current_user_id,
            shelf_id,
            payload.name,
            payload.visibility,
        )
    except ValueError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.delete("/shelves/{shelf_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shelf_route(
    shelf_id: int,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        await delete_shelf(session, current_user_id, shelf_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post("/shelves/{shelf_id}/items", response_model=ShelfItemResponse, status_code=status.HTTP_201_CREATED)
async def add_shelf_item_route(
    shelf_id: int,
    payload: ShelfItemCreateRequest,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        await assert_book_exists(payload.isbn)
        item = await add_shelf_item(
            session,
            current_user_id,
            shelf_id,
            payload.isbn,
            payload.position,
        )
    except ValueError as exc:
        detail = str(exc)
        lowered = detail.lower()
        if "shelf" in lowered and "not found" in lowered:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        if "book" in lowered and "not found" in lowered:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    await track_interaction(
        user_id=current_user_id,
        book_id=payload.isbn,
        qdrant_id=payload.isbn,
        interaction_type="shelf_add",
        value=1.0,
    )

    return item


@router.get("/shelves/{shelf_id}/items", response_model=ShelfItemListResponse)
async def list_shelf_items_route(
    shelf_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        items, total = await list_shelf_items(session, current_user_id, shelf_id, skip=skip, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    payload = [ShelfItemResponse.model_validate(item) for item in items]
    return ShelfItemListResponse(items=payload, total=total)


@router.get("/shelves/{shelf_id}/books", response_model=ShelfBookListResponse)
async def list_shelf_books_route(
    shelf_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        items, total = await list_shelf_items(session, current_user_id, shelf_id, skip=skip, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    payload: list[ShelfBookItemResponse] = []
    for item in items:
        details = {
            "title": None,
            "year": None,
            "author_id": None,
            "author_name": None,
            "publisher": None,
        }
        try:
            details = await get_book_details(item.isbn)
        except ValueError:
            # Keep shelf listing available even if a book is missing/unreachable.
            pass

        payload.append(
            ShelfBookItemResponse(
                id=item.id,
                shelf_id=item.shelf_id,
                isbn=item.isbn,
                position=item.position,
                created_at=item.created_at,
                title=details.get("title"),
                year=details.get("year"),
                author_id=details.get("author_id"),
                author_name=details.get("author_name"),
                publisher=details.get("publisher"),
            )
        )

    return ShelfBookListResponse(items=payload, total=total)


@router.delete("/shelves/{shelf_id}/items/{isbn}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_shelf_item_route(
    shelf_id: int,
    isbn: str,
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        await remove_shelf_item(session, current_user_id, shelf_id, isbn)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
