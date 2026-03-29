import logging
import asyncio

import grpc

from proto import rag_pb2, rag_pb2_grpc

from .mongo_service import add_to_reading_list, rebuild_taste_profile, update_reading_entry
from .v3 import COLLECTION_NAME, add_book_to_database

logger = logging.getLogger(__name__)


def _interaction_to_updates(interaction_type: str, value: float) -> dict:
    normalized = (interaction_type or "").strip().lower()
    if normalized in {"rate", "rating", "rated"}:
        updates = {"status": "read"}
        if value > 0:
            updates["rating"] = float(value)
        return updates
    if normalized in {"like", "liked", "shelf_add", "add_to_shelf", "save", "review"}:
        return {"status": "reading"}
    if normalized in {"want_to_read", "wishlist"}:
        return {"status": "want_to_read"}
    return {"status": "reading"}


class RagServicer(rag_pb2_grpc.RagServiceServicer):
    def __init__(self, db, qdrant_client):
        self._db = db
        self._qdrant_client = qdrant_client

    async def TrackInteraction(self, request, context):
        user_id = str(request.user_id)
        book_id = (request.book_id or "").strip()
        qdrant_id = (request.qdrant_id or "").strip()

        if not user_id or user_id == "0" or not book_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id and book_id are required")

        updates = _interaction_to_updates(request.interaction_type, request.value)

        updated = await update_reading_entry(self._db, user_id, book_id, updates)
        if not updated:
            await add_to_reading_list(
                self._db,
                user_id=user_id,
                book_id=book_id,
                qdrant_id=qdrant_id or book_id,
                title=book_id,
                authors="",
                status=str(updates.get("status", "want_to_read")),
            )
            if "rating" in updates:
                await update_reading_entry(self._db, user_id, book_id, {"rating": updates["rating"]})

        await rebuild_taste_profile(self._db, user_id, self._qdrant_client, COLLECTION_NAME)
        return rag_pb2.TrackInteractionResponse(success=True, message="interaction tracked")

    async def IndexBooks(self, request, context):
        indexed = 0
        failed = 0

        for item in request.books:
            try:
                book_payload = {
                    "book_id": (item.book_id or "").strip(),
                    "id": (item.book_id or "").strip(),
                    "title": item.title,
                    "authors": item.authors,
                    "description": item.description,
                    "categories": list(item.categories or []),
                    "language": item.language,
                    "average_rating": item.average_rating if item.average_rating != 0 else None,
                    "ratings_count": int(item.ratings_count or 0),
                    "published_date": item.published_date,
                    "thumbnail": item.thumbnail,
                    "source": item.source or "bookv2",
                    "author_style": item.author_style,
                }
                await asyncio.to_thread(add_book_to_database, self._qdrant_client, book_payload)
                indexed += 1
            except Exception as exc:
                failed += 1
                logger.warning("RAG IndexBooks failed for '%s': %s", item.book_id, exc)

        return rag_pb2.IndexBooksResponse(
            indexed=indexed,
            failed=failed,
            message="books indexed via gRPC",
        )


async def serve_grpc(db, qdrant_client, host: str = "127.0.0.1", port: int = 50056):
    server = grpc.aio.server()
    rag_pb2_grpc.add_RagServiceServicer_to_server(RagServicer(db, qdrant_client), server)

    listen_addr = f"{host}:{port}"
    bound_port = server.add_insecure_port(listen_addr)
    if bound_port == 0:
        raise RuntimeError(
            f"gRPC failed to bind on {listen_addr}. Is port {port} already in use?"
        )

    await server.start()
    logger.info("RAG gRPC server listening on %s", listen_addr)
    return server

