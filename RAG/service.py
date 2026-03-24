from contextlib import asynccontextmanager
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from .auth import AuthenticatedUser, get_current_user
from .book_grpc_client import close_book_channel, get_book_details
from .config import settings
from .db import close_database, get_database
from .mongo_models import ReadingEntry
from .mongo_service import (
    add_to_reading_list,
    get_book_cache,
    get_read_book_ids,
    get_reading_list,
    rebuild_taste_profile,
    get_taste_profile,
    update_reading_entry,
    upsert_book_cache,
)
from .v3 import (
    COLLECTION_NAME,
    HAS_GOOGLE_API,
    add_book_to_database,
    close_client,
    encoder,
    find_similar_books,
    get_client,
    search_books_by_writer,
    search_database,
    search_google_books_async,
    setup_database,
    suggest_local_books_from_query,
)


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class BookView(BaseModel):
    id: Optional[str] = None
    title: str
    authors: str = ""
    description: str = ""
    categories: List[str] = Field(default_factory=list)
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None
    language: Optional[str] = None
    source: Optional[str] = None
    score: Optional[float] = None


class RecommendationRequest(BaseModel):
    query: str = Field(min_length=1)
    force_external: bool = False
    recommendation_limit: int = Field(default=5, ge=1, le=20)


class RecommendationResponse(BaseModel):
    query: str
    source: str
    external_search_enabled: bool
    target_book: Optional[BookView] = None
    recommendations: List[BookView] = Field(default_factory=list)
    local_suggestions: List[BookView] = Field(default_factory=list)
    message: Optional[str] = None


class WriterSearchResponse(BaseModel):
    writer: str
    source: str = "database"
    external_search_enabled: bool = False
    matches: List[BookView] = Field(default_factory=list)
    selected_book: Optional[BookView] = None
    recommendations: List[BookView] = Field(default_factory=list)
    local_suggestions: List[BookView] = Field(default_factory=list)
    message: Optional[str] = None


class ReadingCreateRequest(BaseModel):
    book_id: str
    title: str
    authors: str
    status: str = Field(default="want_to_read")
    qdrant_id: int


class ReadingUpdateRequest(BaseModel):
    status: Optional[str] = None
    rating: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    notes: Optional[str] = None
    finished_at: Optional[datetime] = None


class ReadingMutationResponse(BaseModel):
    success: bool
    message: Optional[str] = None


class PersonalizedRecommendationResponse(BaseModel):
    user_id: str
    source: str
    recommendations: List[BookView] = Field(default_factory=list)
    message: Optional[str] = None


class InteractionEventRequest(BaseModel):
    user_id: str
    book_id: str
    qdrant_id: int
    interaction_type: str
    value: Optional[float] = None


class InteractionEventResponse(BaseModel):
    success: bool
    message: Optional[str] = None


def _payload_from_obj(item: Any) -> Dict[str, Any]:
    if hasattr(item, "payload"):
        payload = item.payload or {}
        payload = dict(payload)
        item_id = getattr(item, "id", None)
        payload.setdefault("id", str(item_id) if item_id is not None else None)
        if hasattr(item, "score") and item.score is not None:
            payload["score"] = float(item.score)
        return payload
    if isinstance(item, dict):
        return dict(item)
    return {}


def _to_book_view(item: Any) -> BookView:
    payload = _payload_from_obj(item)
    categories = payload.get("categories") or []
    if not isinstance(categories, list):
        categories = [str(categories)]

    return BookView(
        id=(str(payload.get("id")) if payload.get("id") is not None else None),
        title=str(payload.get("title", "Unknown")),
        authors=str(payload.get("authors", "")),
        description=str(payload.get("description", "")),
        categories=[str(c) for c in categories],
        average_rating=(float(payload["average_rating"]) if payload.get("average_rating") is not None else None),
        ratings_count=(int(payload["ratings_count"]) if payload.get("ratings_count") is not None else None),
        language=payload.get("language"),
        source=payload.get("source"),
        score=(float(payload["score"]) if payload.get("score") is not None else None),
    )


def _extract_point_vector(point: Any) -> Optional[List[float]]:
    vector_data = getattr(point, "vector", None)
    if isinstance(vector_data, dict):
        vec = vector_data.get("book_content") or vector_data.get("author_style")
    else:
        vec = vector_data

    if not vec:
        return None

    try:
        values = [float(v) for v in vec]
    except (TypeError, ValueError):
        return None

    return values if len(values) == 384 else None


async def _query_books_with_vector(client: QdrantClient, vector: List[float], limit: int) -> List[Any]:
    try:
        return await asyncio.to_thread(
            lambda: client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                using="book_content",
                limit=limit,
                with_payload=True,
            ).points
        )
    except Exception:
        return await asyncio.to_thread(
            lambda: client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                limit=limit,
                with_payload=True,
            ).points
        )


async def _generic_recommendations(client: QdrantClient, limit: int = 10) -> List[Any]:
    query_vector = await asyncio.to_thread(lambda: encoder.encode("popular books").tolist())
    return await _query_books_with_vector(client, query_vector, max(limit, 20))



def _interaction_to_updates(interaction_type: str, value: Optional[float]) -> Dict[str, Any]:
    normalized = (interaction_type or "").strip().lower()
    if normalized in {"rate", "rating", "rated"}:
        updates: Dict[str, Any] = {"status": "read"}
        if value is not None:
            updates["rating"] = float(value)
        return updates
    if normalized in {"like", "liked", "shelf_add", "add_to_shelf", "save"}:
        return {"status": "reading"}
    if normalized in {"want_to_read", "wishlist"}:
        return {"status": "want_to_read"}
    return {"status": "reading"}


def _ensure_user_access(path_user_id: str, current_user: AuthenticatedUser) -> None:
    if current_user.is_superuser:
        return
    if str(current_user.id) != str(path_user_id):
        raise HTTPException(status_code=403, detail="Forbidden for this user")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = await asyncio.to_thread(get_client)
    await asyncio.to_thread(setup_database, client)
    await get_database()
    yield
    await asyncio.to_thread(lambda: close_client(client))
    await close_book_channel()
    await close_database()


async def get_request_client():
    client = await asyncio.to_thread(get_client)
    try:
        yield client
    finally:
        await asyncio.to_thread(lambda: close_client(client))


async def get_db():
    return await get_database()


app = FastAPI(
    title="RAG Recommendation Service",
    description="HTTP service wrapper around the RAG v3 recommendation pipeline.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health(client: QdrantClient = Depends(get_request_client)) -> Dict[str, Any]:
    try:
        total = await asyncio.to_thread(
            lambda: client.count(collection_name=COLLECTION_NAME, exact=False).count
        )
    except Exception as exc:
        logger.warning("Health count lookup failed: %s", exc)
        total = None
    return {
        "status": "ok",
        "external_search_enabled": HAS_GOOGLE_API,
        "collection": COLLECTION_NAME,
        "books": total,
    }


@app.post("/api/v1/recommend", response_model=RecommendationResponse)
async def recommend(
    payload: RecommendationRequest,
    client: QdrantClient = Depends(get_request_client),
) -> RecommendationResponse:
    normalized = payload.query.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="book name is required")

    db_matches = await asyncio.to_thread(search_database, client, normalized)

    if db_matches and not payload.force_external:
        target = db_matches[0]["book"]
        recommendations = await asyncio.to_thread(
            find_similar_books,
            client,
            target,
            payload.recommendation_limit,
        )
        return RecommendationResponse(
            query=normalized,
            source="database",
            external_search_enabled=HAS_GOOGLE_API,
            target_book=_to_book_view(target),
            recommendations=[_to_book_view(r) for r in recommendations],
        )

    if not HAS_GOOGLE_API:
        fallback = await asyncio.to_thread(
            suggest_local_books_from_query,
            client,
            normalized,
            payload.recommendation_limit,
        )
        return RecommendationResponse(
            query=normalized,
            source="none",
            external_search_enabled=False,
            message="Google Books API key is not configured. Returning local semantic suggestions.",
            local_suggestions=[_to_book_view(x) for x in fallback],
        )

    api_results = await search_google_books_async(normalized, max_results=5)
    if not api_results:
        fallback = await asyncio.to_thread(
            suggest_local_books_from_query,
            client,
            normalized,
            payload.recommendation_limit,
        )
        return RecommendationResponse(
            query=normalized,
            source="none",
            external_search_enabled=True,
            message="No external results found. Returning local semantic suggestions.",
            local_suggestions=[_to_book_view(x) for x in fallback],
        )

    selected = api_results[0]
    await asyncio.to_thread(add_book_to_database, client, selected)
    recommendations = await asyncio.to_thread(
        find_similar_books,
        client,
        selected,
        payload.recommendation_limit,
    )

    return RecommendationResponse(
        query=normalized,
        source="external_added",
        external_search_enabled=True,
        target_book=_to_book_view(selected),
        recommendations=[_to_book_view(r) for r in recommendations],
    )


@app.get("/api/v1/books/recommend", response_model=RecommendationResponse)
async def recommend_book_by_name(
    name: str = Query(..., min_length=1),
    force_external: bool = Query(False),
    recommendation_limit: int = Query(5, ge=1, le=20),
    client: QdrantClient = Depends(get_request_client),
) -> RecommendationResponse:
    return await recommend(
        RecommendationRequest(
            query=name,
            force_external=force_external,
            recommendation_limit=recommendation_limit,
        ),
        client,
    )


@app.get("/api/v1/writers/search", response_model=WriterSearchResponse)
async def writer_search(
    name: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    selected_index: int = Query(1, ge=1),
    recommendation_limit: int = Query(5, ge=1, le=20),
    client: QdrantClient = Depends(get_request_client),
) -> WriterSearchResponse:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="writer name is required")

    books = await asyncio.to_thread(search_books_by_writer, client, normalized, limit)
    if books:
        idx = min(selected_index - 1, len(books) - 1)
        selected = books[idx]
        recommendations = await asyncio.to_thread(
            find_similar_books,
            client,
            selected,
            recommendation_limit,
        )
        return WriterSearchResponse(
            writer=normalized,
            source="database",
            external_search_enabled=HAS_GOOGLE_API,
            matches=[_to_book_view(b) for b in books],
            selected_book=_to_book_view(selected),
            recommendations=[_to_book_view(r) for r in recommendations],
        )

    if not HAS_GOOGLE_API:
        fallback = await asyncio.to_thread(
            suggest_local_books_from_query,
            client,
            normalized,
            recommendation_limit,
        )
        return WriterSearchResponse(
            writer=normalized,
            source="none",
            external_search_enabled=False,
            message="Google Books API key is not configured. Returning local semantic suggestions.",
            local_suggestions=[_to_book_view(x) for x in fallback],
        )

    api_results = await search_google_books_async(f'inauthor:"{normalized}"', max_results=min(limit, 10))
    if not api_results:
        fallback = await asyncio.to_thread(
            suggest_local_books_from_query,
            client,
            normalized,
            recommendation_limit,
        )
        return WriterSearchResponse(
            writer=normalized,
            source="none",
            external_search_enabled=True,
            message="No external writer results found. Returning local semantic suggestions.",
            local_suggestions=[_to_book_view(x) for x in fallback],
        )

    selected = api_results[0]
    await asyncio.to_thread(add_book_to_database, client, selected)
    recommendations = await asyncio.to_thread(
        find_similar_books,
        client,
        selected,
        recommendation_limit,
    )

    return WriterSearchResponse(
        writer=normalized,
        source="external_added",
        external_search_enabled=True,
        matches=[_to_book_view(b) for b in api_results],
        selected_book=_to_book_view(selected),
        recommendations=[_to_book_view(r) for r in recommendations],
    )


@app.get("/api/v1/writers/recommend", response_model=WriterSearchResponse)
async def recommend_writer_by_name(
    name: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    selected_index: int = Query(1, ge=1),
    recommendation_limit: int = Query(5, ge=1, le=20),
    client: QdrantClient = Depends(get_request_client),
) -> WriterSearchResponse:
    return await writer_search(
        name=name,
        limit=limit,
        selected_index=selected_index,
        recommendation_limit=recommendation_limit,
        client=client,
    )


@app.post("/api/v1/users/{user_id}/readings", response_model=ReadingMutationResponse)
async def create_reading_entry(
    user_id: str,
    payload: ReadingCreateRequest,
    db=Depends(get_db),
    client: QdrantClient = Depends(get_request_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ReadingMutationResponse:
    _ensure_user_access(user_id, current_user)

    # Pull canonical metadata from Book service over gRPC when available.
    grpc_book = await get_book_details(payload.book_id)

    book_doc = {
        "book_id": (grpc_book or {}).get("book_id", payload.book_id),
        "qdrant_id": payload.qdrant_id,
        "title": (grpc_book or {}).get("title") or payload.title,
        "authors": (grpc_book or {}).get("authors") or payload.authors,
        "description": "",
        "categories": [],
        "language": "unknown",
        "average_rating": None,
        "ratings_count": None,
        "thumbnail": "",
        "source": (grpc_book or {}).get("source", "google_books"),
    }
    cached = await get_book_cache(db, payload.book_id)
    if cached:
        book_doc.update(cached)

    await upsert_book_cache(db, book_doc)
    await add_to_reading_list(
        db,
        user_id=user_id,
        book_id=payload.book_id,
        qdrant_id=payload.qdrant_id,
        title=book_doc["title"],
        authors=book_doc["authors"],
        status=payload.status,
    )
    await rebuild_taste_profile(db, user_id, client, COLLECTION_NAME)
    return ReadingMutationResponse(success=True)


@app.get("/api/v1/users/{user_id}/readings", response_model=List[ReadingEntry])
async def list_reading_entries(
    user_id: str,
    status: Optional[str] = Query(default=None),
    db=Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[ReadingEntry]:
    _ensure_user_access(user_id, current_user)
    rows = await get_reading_list(db, user_id, status=status)
    return [ReadingEntry.model_validate(row) for row in rows]


@app.patch("/api/v1/users/{user_id}/readings/{book_id}", response_model=ReadingMutationResponse)
async def patch_reading_entry(
    user_id: str,
    book_id: str,
    payload: ReadingUpdateRequest,
    db=Depends(get_db),
    client: QdrantClient = Depends(get_request_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ReadingMutationResponse:
    _ensure_user_access(user_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    updated = await update_reading_entry(db, user_id, book_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="reading entry not found")
    await rebuild_taste_profile(db, user_id, client, COLLECTION_NAME)
    return ReadingMutationResponse(success=True)


@app.delete("/api/v1/users/{user_id}/readings/{book_id}", response_model=ReadingMutationResponse)
async def delete_reading_entry(
    user_id: str,
    book_id: str,
    db=Depends(get_db),
    client: QdrantClient = Depends(get_request_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ReadingMutationResponse:
    _ensure_user_access(user_id, current_user)
    result = await db["reading_list"].delete_one({"user_id": user_id, "book_id": book_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="reading entry not found")
    await rebuild_taste_profile(db, user_id, client, COLLECTION_NAME)
    return ReadingMutationResponse(success=True)


@app.get("/api/v1/users/{user_id}/recommend", response_model=PersonalizedRecommendationResponse)
async def personalized_recommend(
    user_id: str,
    db=Depends(get_db),
    client: QdrantClient = Depends(get_request_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PersonalizedRecommendationResponse:
    _ensure_user_access(user_id, current_user)
    profile = await get_taste_profile(db, user_id)

    if not profile or not isinstance(profile.get("vector"), list) or profile.get("book_count", 0) <= 0:
        generic_hits = await _generic_recommendations(client, limit=10)
        return PersonalizedRecommendationResponse(
            user_id=user_id,
            source="generic_fallback",
            recommendations=[_to_book_view(hit) for hit in generic_hits[:10]],
            message="No taste profile yet. Returning generic recommendations.",
        )

    vector = [float(v) for v in profile["vector"]]
    if len(vector) != 384:
        generic_hits = await _generic_recommendations(client, limit=10)
        return PersonalizedRecommendationResponse(
            user_id=user_id,
            source="generic_fallback",
            recommendations=[_to_book_view(hit) for hit in generic_hits[:10]],
            message="Taste profile vector is invalid. Returning generic recommendations.",
        )

    read_book_ids = set(await get_read_book_ids(db, user_id))
    reading_entries = await get_reading_list(db, user_id)
    read_qdrant_ids = {str(entry.get("qdrant_id")) for entry in reading_entries if entry.get("qdrant_id") is not None}

    hits = await _query_books_with_vector(client, vector, limit=80)
    filtered: List[Any] = []
    for hit in hits:
        payload = hit.payload or {}
        payload_book_id = payload.get("book_id")
        if payload_book_id and str(payload_book_id) in read_book_ids:
            continue
        if str(hit.id) in read_qdrant_ids:
            continue
        filtered.append(hit)
        if len(filtered) >= 10:
            break

    if not filtered:
        fallback_hits = await _generic_recommendations(client, limit=10)
        return PersonalizedRecommendationResponse(
            user_id=user_id,
            source="generic_fallback",
            recommendations=[_to_book_view(hit) for hit in fallback_hits[:10]],
            message="No personalized candidates left after exclusions. Returning generic recommendations.",
        )

    return PersonalizedRecommendationResponse(
        user_id=user_id,
        source="personalized",
        recommendations=[_to_book_view(hit) for hit in filtered],
    )


@app.post("/api/v1/internal/interactions", response_model=InteractionEventResponse)
async def ingest_internal_interaction(
    payload: InteractionEventRequest,
    db=Depends(get_db),
    client: QdrantClient = Depends(get_request_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> InteractionEventResponse:
    if not current_user.is_superuser and str(current_user.id) != str(payload.user_id):
        raise HTTPException(status_code=403, detail="Forbidden for this user")

    updates = _interaction_to_updates(payload.interaction_type, payload.value)
    grpc_book = await get_book_details(payload.book_id)

    updated = await update_reading_entry(db, payload.user_id, payload.book_id, updates)
    if not updated:
        await add_to_reading_list(
            db,
            user_id=payload.user_id,
            book_id=payload.book_id,
            qdrant_id=payload.qdrant_id,
            title=(grpc_book or {}).get("title") or payload.book_id,
            authors=(grpc_book or {}).get("authors") or "",
            status=str(updates.get("status", "want_to_read")),
        )
        if "rating" in updates:
            await update_reading_entry(db, payload.user_id, payload.book_id, {"rating": updates["rating"]})

    await rebuild_taste_profile(db, payload.user_id, client, COLLECTION_NAME)
    return InteractionEventResponse(success=True)


