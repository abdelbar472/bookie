from datetime import datetime, timezone
import math
from typing import Any

from .db import (
    get_book_cache_collection,
    get_reading_list_collection,
    get_taste_profiles_collection,
)

_ALLOWED_STATUS = {"read", "reading", "want_to_read"}
_INTERACTION_WEIGHTS = {
    "read": 1.0,
    "reading": 0.6,
    "want_to_read": 0.2,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_interaction_weight(status: str, rating: float | None = None) -> float:
    # Current weighting is status-driven; rating changes still trigger recompute.
    _ = rating
    return _INTERACTION_WEIGHTS.get(status, _INTERACTION_WEIGHTS["want_to_read"])


def _validate_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized not in _ALLOWED_STATUS:
        raise ValueError(f"Invalid status '{status}'. Allowed: {sorted(_ALLOWED_STATUS)}")
    return normalized


def _validate_rating(rating: Any) -> float | None:
    if rating is None:
        return None
    value = float(rating)
    if value < 1.0 or value > 5.0:
        raise ValueError("rating must be between 1.0 and 5.0")
    return value


def _extract_named_vector(vector_data: Any, key: str) -> list[float] | None:
    if isinstance(vector_data, dict):
        vec = vector_data.get(key)
    else:
        vec = vector_data

    if not vec:
        return None

    try:
        values = [float(v) for v in vec]
    except (TypeError, ValueError):
        return None

    return values if len(values) == 384 else None


def _extract_book_vector(point: Any) -> list[float] | None:
    """Extract the book_content vector (or fallback vector) from a Qdrant point."""
    vector_data = getattr(point, "vector", None)
    primary = _extract_named_vector(vector_data, "book_content")
    if primary:
        return primary
    return _extract_named_vector(vector_data, "author_style")


def _extract_author_style_vector(point: Any) -> list[float] | None:
    vector_data = getattr(point, "vector", None)
    return _extract_named_vector(vector_data, "author_style")


async def upsert_book_cache(db, book: dict) -> str:
    """Insert or update a book cache entry by book_id."""
    if not isinstance(book, dict):
        raise ValueError("book must be a dict")

    book_id = str(book.get("book_id", "")).strip()
    if not book_id:
        raise ValueError("book_id is required")

    payload = dict(book)
    payload["book_id"] = book_id

    collection = get_book_cache_collection(db)
    await collection.update_one(
        {"book_id": book_id},
        {"$set": payload},
        upsert=True,
    )
    return book_id


async def get_book_cache(db, book_id: str) -> dict | None:
    """Fetch one book from cache by book_id."""
    key = (book_id or "").strip()
    if not key:
        return None

    collection = get_book_cache_collection(db)
    return await collection.find_one({"book_id": key}, {"_id": 0})


async def add_to_reading_list(
    db,
    user_id: str,
    book_id: str,
    qdrant_id: str | int,
    title: str,
    authors: str,
    status: str = "want_to_read",
) -> bool:
    """Upsert reading list entry by compound key (user_id, book_id)."""
    user_key = (user_id or "").strip()
    book_key = (book_id or "").strip()
    if not user_key or not book_key:
        raise ValueError("user_id and book_id are required")

    status_value = _validate_status(status)
    interaction_weight = _compute_interaction_weight(status_value)

    now = _utcnow()
    set_values = {
        "qdrant_id": str(qdrant_id),
        "title": (title or "").strip(),
        "authors": (authors or "").strip(),
        "status": status_value,
        "interaction_weight": interaction_weight,
    }

    if status_value == "read":
        set_values["finished_at"] = now

    collection = get_reading_list_collection(db)
    result = await collection.update_one(
        {"user_id": user_key, "book_id": book_key},
        {
            "$set": set_values,
            "$setOnInsert": {
                "user_id": user_key,
                "book_id": book_key,
                "added_at": now,
            },
        },
        upsert=True,
    )
    return bool(result.acknowledged)


async def get_reading_list(db, user_id: str, status: str | None = None) -> list[dict]:
    """Fetch all reading entries for a user, optionally filtered by status."""
    user_key = (user_id or "").strip()
    if not user_key:
        return []

    query: dict[str, Any] = {"user_id": user_key}
    if status is not None:
        query["status"] = _validate_status(status)

    collection = get_reading_list_collection(db)
    cursor = collection.find(query, {"_id": 0}).sort("added_at", -1)
    return await cursor.to_list(length=None)


async def update_reading_entry(db, user_id: str, book_id: str, updates: dict) -> bool:
    """Update reading_list fields and recompute interaction_weight when needed."""
    user_key = (user_id or "").strip()
    book_key = (book_id or "").strip()
    if not user_key or not book_key:
        raise ValueError("user_id and book_id are required")

    if not isinstance(updates, dict) or not updates:
        return False

    collection = get_reading_list_collection(db)
    current = await collection.find_one(
        {"user_id": user_key, "book_id": book_key},
        {"_id": 0, "status": 1, "rating": 1, "interaction_weight": 1},
    )
    if not current:
        return False

    allowed_fields = {"status", "rating", "notes", "finished_at"}
    set_values: dict[str, Any] = {}

    for key, value in updates.items():
        if key not in allowed_fields:
            continue

        if key == "status":
            set_values["status"] = _validate_status(str(value))
        elif key == "rating":
            set_values["rating"] = _validate_rating(value)
        elif key == "notes":
            set_values["notes"] = None if value is None else str(value)
        elif key == "finished_at":
            set_values["finished_at"] = value

    if not set_values:
        return False

    status_changed = "status" in set_values
    rating_changed = "rating" in set_values

    effective_status = set_values.get("status", current.get("status", "want_to_read"))
    effective_rating = set_values.get("rating", current.get("rating"))

    if status_changed or rating_changed:
        set_values["interaction_weight"] = _compute_interaction_weight(effective_status, effective_rating)

    if status_changed and effective_status == "read" and "finished_at" not in set_values:
        set_values["finished_at"] = _utcnow()

    if status_changed and effective_status != "read" and "finished_at" not in set_values:
        set_values["finished_at"] = None

    result = await collection.update_one(
        {"user_id": user_key, "book_id": book_key},
        {"$set": set_values},
    )
    return bool(result.acknowledged and (result.modified_count > 0 or result.matched_count > 0))


async def upsert_taste_profile(db, user_id: str, vector: list[float], book_count: int):
    """Insert or update user taste profile."""
    user_key = (user_id or "").strip()
    if not user_key:
        raise ValueError("user_id is required")

    if not isinstance(vector, list) or len(vector) != 384:
        raise ValueError("vector must contain exactly 384 float values")

    vector_values = [float(v) for v in vector]

    collection = get_taste_profiles_collection(db)
    await collection.update_one(
        {"user_id": user_key},
        {
            "$set": {
                "vector": vector_values,
                "book_count": int(book_count),
                "updated_at": _utcnow(),
            },
            "$setOnInsert": {
                "user_id": user_key,
            },
        },
        upsert=True,
    )


async def get_taste_profile(db, user_id: str) -> dict | None:
    """Fetch taste profile by user_id."""
    user_key = (user_id or "").strip()
    if not user_key:
        return None

    collection = get_taste_profiles_collection(db)
    return await collection.find_one({"user_id": user_key}, {"_id": 0})


async def get_read_book_ids(db, user_id: str) -> list[str]:
    """Return book IDs for entries that are read or currently reading."""
    user_key = (user_id or "").strip()
    if not user_key:
        return []

    collection = get_reading_list_collection(db)
    cursor = collection.find(
        {
            "user_id": user_key,
            "status": {"$in": ["read", "reading"]},
        },
        {"_id": 0, "book_id": 1},
    )
    rows = await cursor.to_list(length=None)
    return [str(row.get("book_id")) for row in rows if row.get("book_id")]


async def rebuild_taste_profile(db, user_id: str, qdrant_client, collection_name: str):
    """Rebuild user's taste profile from reading history and current Qdrant vectors."""
    entries = await get_reading_list(db, user_id)
    if not entries:
        return

    weighted_entries: list[tuple[str, float]] = []
    for entry in entries:
        qdrant_id = entry.get("qdrant_id")
        if qdrant_id is None:
            continue

        status = _validate_status(str(entry.get("status", "want_to_read")))
        status_weight = _INTERACTION_WEIGHTS.get(status, _INTERACTION_WEIGHTS["want_to_read"])
        rating = _validate_rating(entry.get("rating"))
        score_factor = (rating / 5.0) if rating is not None else 0.8
        weight = status_weight * score_factor
        if weight <= 0:
            continue

        weighted_entries.append((str(qdrant_id), weight))

    if not weighted_entries:
        return

    # Build candidate ID list and query with string IDs first, then int IDs as fallback.
    unique_ids = list({qid for qid, _ in weighted_entries})
    points = []
    try:
        points = qdrant_client.retrieve(
            collection_name=collection_name,
            ids=unique_ids,
            with_vectors=True,
            with_payload=False,
        )
    except Exception:
        int_ids = []
        for qid in unique_ids:
            try:
                int_ids.append(int(qid))
            except (TypeError, ValueError):
                continue

        if int_ids:
            try:
                points = qdrant_client.retrieve(
                    collection_name=collection_name,
                    ids=int_ids,
                    with_vectors=True,
                    with_payload=False,
                )
            except Exception:
                points = []

    if not points:
        return

    point_map = {str(point.id): point for point in points}
    weighted_sum = [0.0] * 384
    total_weight = 0.0

    for qid, weight in weighted_entries:
        point = point_map.get(qid)
        if not point:
            # qdrant_id may no longer exist; skip safely.
            continue

        book_vec = _extract_book_vector(point)
        author_vec = _extract_author_style_vector(point)
        if not book_vec and not author_vec:
            continue

        # Blend dynamic content signal with static author-style signal.
        if book_vec and author_vec:
            vector = [(0.7 * b) + (0.3 * a) for b, a in zip(book_vec, author_vec)]
        else:
            vector = book_vec or author_vec

        for idx, value in enumerate(vector):
            weighted_sum[idx] += weight * value
        total_weight += weight

    if total_weight <= 0:
        return

    averaged_vector = [value / total_weight for value in weighted_sum]

    # L2 normalization of final profile vector.
    norm = math.sqrt(sum(value * value for value in averaged_vector))
    if norm > 0:
        averaged_vector = [value / norm for value in averaged_vector]

    await upsert_taste_profile(db, user_id, averaged_vector, len(entries))


