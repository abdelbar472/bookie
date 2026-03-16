from datetime import datetime, timezone
from typing import Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BookLike, BookRating, BookReview, ReviewLike, Shelf, ShelfItem


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def like_book(session: AsyncSession, user_id: int, isbn: str) -> BookLike:
    existing = (
        await session.execute(
            select(BookLike).where(BookLike.user_id == user_id, BookLike.isbn == isbn)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    row = BookLike(user_id=user_id, isbn=isbn)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def unlike_book(session: AsyncSession, user_id: int, isbn: str) -> bool:
    row = (
        await session.execute(
            select(BookLike).where(BookLike.user_id == user_id, BookLike.isbn == isbn)
        )
    ).scalar_one_or_none()
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def upsert_rating(session: AsyncSession, user_id: int, isbn: str, rating: float) -> BookRating:
    row = (
        await session.execute(
            select(BookRating).where(BookRating.user_id == user_id, BookRating.isbn == isbn)
        )
    ).scalar_one_or_none()
    now = utc_now()
    if row:
        row.rating = rating
        row.updated_at = now
    else:
        row = BookRating(user_id=user_id, isbn=isbn, rating=rating, created_at=now, updated_at=now)
        session.add(row)

    await session.commit()
    await session.refresh(row)
    return row


async def get_my_rating(session: AsyncSession, user_id: int, isbn: str) -> BookRating | None:
    return (
        await session.execute(
            select(BookRating).where(BookRating.user_id == user_id, BookRating.isbn == isbn)
        )
    ).scalar_one_or_none()


async def create_review(
    session: AsyncSession,
    user_id: int,
    isbn: str,
    title: str,
    content: str,
) -> BookReview:
    row = BookReview(user_id=user_id, isbn=isbn, title=title, content=content)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def create_review_reply(
    session: AsyncSession,
    user_id: int,
    parent_review_id: int,
    title: str,
    content: str,
) -> BookReview:
    parent = (
        await session.execute(select(BookReview).where(BookReview.id == parent_review_id))
    ).scalar_one_or_none()
    if not parent:
        raise ValueError("Parent review not found")

    row = BookReview(
        user_id=user_id,
        isbn=parent.isbn,
        parent_review_id=parent_review_id,
        title=title,
        content=content,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_review(
    session: AsyncSession,
    user_id: int,
    review_id: int,
    title: str | None,
    content: str | None,
) -> BookReview:
    row = (
        await session.execute(select(BookReview).where(BookReview.id == review_id))
    ).scalar_one_or_none()
    if not row:
        raise ValueError("Review not found")
    if row.user_id != user_id:
        raise PermissionError("You can edit only your own review")

    if title is not None:
        row.title = title
    if content is not None:
        row.content = content
    row.updated_at = utc_now()

    await session.commit()
    await session.refresh(row)
    return row


async def delete_review(session: AsyncSession, user_id: int, review_id: int) -> None:
    row = (
        await session.execute(select(BookReview).where(BookReview.id == review_id))
    ).scalar_one_or_none()
    if not row:
        raise ValueError("Review not found")
    if row.user_id != user_id:
        raise PermissionError("You can delete only your own review")

    # Remove child replies and likes for a predictable one-shot delete behavior.
    replies = (
        await session.execute(select(BookReview).where(BookReview.parent_review_id == review_id))
    ).scalars().all()
    reply_ids = [r.id for r in replies if r.id is not None]
    if reply_ids:
        reply_likes = (
            await session.execute(select(ReviewLike).where(ReviewLike.review_id.in_(reply_ids)))
        ).scalars().all()
        for row_like in reply_likes:
            await session.delete(row_like)
        for reply in replies:
            await session.delete(reply)

    likes = (
        await session.execute(select(ReviewLike).where(ReviewLike.review_id == review_id))
    ).scalars().all()
    for row_like in likes:
        await session.delete(row_like)

    await session.delete(row)
    await session.commit()


async def list_book_reviews(
    session: AsyncSession,
    isbn: str,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[list[BookReview], int]:
    total = (
        await session.execute(
            select(func.count())
            .select_from(BookReview)
            .where(BookReview.isbn == isbn, BookReview.parent_review_id.is_(None))
        )
    ).scalar_one()

    rows = (
        await session.execute(
            select(BookReview)
            .where(BookReview.isbn == isbn, BookReview.parent_review_id.is_(None))
            .order_by(BookReview.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)


async def list_review_replies(
    session: AsyncSession,
    parent_review_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[list[BookReview], int]:
    parent = (
        await session.execute(select(BookReview).where(BookReview.id == parent_review_id))
    ).scalar_one_or_none()
    if not parent:
        raise ValueError("Review not found")

    total = (
        await session.execute(
            select(func.count())
            .select_from(BookReview)
            .where(BookReview.parent_review_id == parent_review_id)
        )
    ).scalar_one()

    rows = (
        await session.execute(
            select(BookReview)
            .where(BookReview.parent_review_id == parent_review_id)
            .order_by(BookReview.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)


async def like_review(session: AsyncSession, user_id: int, review_id: int) -> ReviewLike:
    review = (
        await session.execute(select(BookReview).where(BookReview.id == review_id))
    ).scalar_one_or_none()
    if not review:
        raise ValueError("Review not found")

    existing = (
        await session.execute(
            select(ReviewLike).where(ReviewLike.user_id == user_id, ReviewLike.review_id == review_id)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    row = ReviewLike(user_id=user_id, review_id=review_id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def unlike_review(session: AsyncSession, user_id: int, review_id: int) -> bool:
    row = (
        await session.execute(
            select(ReviewLike).where(ReviewLike.user_id == user_id, ReviewLike.review_id == review_id)
        )
    ).scalar_one_or_none()
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_review_metrics(session: AsyncSession, review_ids: list[int]) -> dict[int, dict[str, int]]:
    if not review_ids:
        return {}

    like_rows = (
        await session.execute(
            select(ReviewLike.review_id, func.count(ReviewLike.id))
            .where(ReviewLike.review_id.in_(review_ids))
            .group_by(ReviewLike.review_id)
        )
    ).all()

    reply_rows = (
        await session.execute(
            select(BookReview.parent_review_id, func.count(BookReview.id))
            .where(BookReview.parent_review_id.in_(review_ids))
            .group_by(BookReview.parent_review_id)
        )
    ).all()

    metrics = {rid: {"likes_count": 0, "replies_count": 0} for rid in review_ids}
    for review_id, count in like_rows:
        metrics[int(review_id)]["likes_count"] = int(count)
    for parent_review_id, count in reply_rows:
        if parent_review_id is not None:
            metrics[int(parent_review_id)]["replies_count"] = int(count)

    return metrics


async def create_shelf(session: AsyncSession, user_id: int, name: str, visibility: str) -> Shelf:
    existing = (
        await session.execute(select(Shelf).where(Shelf.user_id == user_id, Shelf.name == name))
    ).scalar_one_or_none()
    if existing:
        raise ValueError("Shelf name already exists")

    row = Shelf(user_id=user_id, name=name, visibility=visibility)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_my_shelves(
    session: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[list[Shelf], int]:
    total = (
        await session.execute(select(func.count()).select_from(Shelf).where(Shelf.user_id == user_id))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Shelf)
            .where(Shelf.user_id == user_id)
            .order_by(Shelf.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)


async def update_shelf(
    session: AsyncSession,
    user_id: int,
    shelf_id: int,
    name: str | None,
    visibility: str | None,
) -> Shelf:
    shelf = (await session.execute(select(Shelf).where(Shelf.id == shelf_id))).scalar_one_or_none()
    if not shelf:
        raise ValueError("Shelf not found")
    if shelf.user_id != user_id:
        raise PermissionError("You can edit only your own shelf")

    if name is not None and name != shelf.name:
        dup = (
            await session.execute(select(Shelf).where(Shelf.user_id == user_id, Shelf.name == name))
        ).scalar_one_or_none()
        if dup:
            raise ValueError("Shelf name already exists")
        shelf.name = name

    if visibility is not None:
        shelf.visibility = visibility

    shelf.updated_at = utc_now()
    await session.commit()
    await session.refresh(shelf)
    return shelf


async def delete_shelf(session: AsyncSession, user_id: int, shelf_id: int) -> None:
    shelf = (await session.execute(select(Shelf).where(Shelf.id == shelf_id))).scalar_one_or_none()
    if not shelf:
        raise ValueError("Shelf not found")
    if shelf.user_id != user_id:
        raise PermissionError("You can delete only your own shelf")

    items = (
        await session.execute(select(ShelfItem).where(ShelfItem.shelf_id == shelf_id))
    ).scalars().all()
    for item in items:
        await session.delete(item)
    await session.delete(shelf)
    await session.commit()


async def add_shelf_item(
    session: AsyncSession,
    user_id: int,
    shelf_id: int,
    isbn: str,
    position: int,
) -> ShelfItem:
    shelf = (await session.execute(select(Shelf).where(Shelf.id == shelf_id))).scalar_one_or_none()
    if not shelf:
        raise ValueError("Shelf not found")
    if shelf.user_id != user_id:
        raise PermissionError("You can modify only your own shelf")

    existing = (
        await session.execute(
            select(ShelfItem).where(ShelfItem.shelf_id == shelf_id, ShelfItem.isbn == isbn)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    row = ShelfItem(shelf_id=shelf_id, isbn=isbn, position=position)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_shelf_items(
    session: AsyncSession,
    user_id: int,
    shelf_id: int,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[list[ShelfItem], int]:
    shelf = (await session.execute(select(Shelf).where(Shelf.id == shelf_id))).scalar_one_or_none()
    if not shelf:
        raise ValueError("Shelf not found")
    if shelf.user_id != user_id and shelf.visibility != "public":
        raise PermissionError("Shelf is private")

    total = (
        await session.execute(
            select(func.count()).select_from(ShelfItem).where(ShelfItem.shelf_id == shelf_id)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(ShelfItem)
            .where(ShelfItem.shelf_id == shelf_id)
            .order_by(ShelfItem.position.asc(), ShelfItem.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)


async def remove_shelf_item(session: AsyncSession, user_id: int, shelf_id: int, isbn: str) -> None:
    shelf = (await session.execute(select(Shelf).where(Shelf.id == shelf_id))).scalar_one_or_none()
    if not shelf:
        raise ValueError("Shelf not found")
    if shelf.user_id != user_id:
        raise PermissionError("You can modify only your own shelf")

    item = (
        await session.execute(
            select(ShelfItem).where(ShelfItem.shelf_id == shelf_id, ShelfItem.isbn == isbn)
        )
    ).scalar_one_or_none()
    if not item:
        raise ValueError("Shelf item not found")

    await session.delete(item)
    await session.commit()


async def get_book_social_stats(session: AsyncSession, isbn: str) -> dict:
    likes_count = (
        await session.execute(
            select(func.count()).select_from(BookLike).where(BookLike.isbn == isbn)
        )
    ).scalar_one()

    rating_agg = (
        await session.execute(
            select(func.count(BookRating.id), func.avg(BookRating.rating)).where(BookRating.isbn == isbn)
        )
    ).one()

    ratings_count = int(rating_agg[0] or 0)
    avg_rating = float(rating_agg[1]) if rating_agg[1] is not None else None

    return {
        "isbn": isbn,
        "likes_count": int(likes_count),
        "ratings_count": ratings_count,
        "avg_rating": avg_rating,
    }

