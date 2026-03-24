import logging

import grpc

from proto import rag_pb2, rag_pb2_grpc

from .mongo_service import add_to_reading_list, rebuild_taste_profile, update_reading_entry
from .v3 import COLLECTION_NAME

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
            try:
                qdrant_as_int = int(qdrant_id)
            except (TypeError, ValueError):
                qdrant_as_int = 0

            await add_to_reading_list(
                self._db,
                user_id=user_id,
                book_id=book_id,
                qdrant_id=qdrant_as_int,
                title=book_id,
                authors="",
                status=str(updates.get("status", "want_to_read")),
            )
            if "rating" in updates:
                await update_reading_entry(self._db, user_id, book_id, {"rating": updates["rating"]})

        await rebuild_taste_profile(self._db, user_id, self._qdrant_client, COLLECTION_NAME)
        return rag_pb2.TrackInteractionResponse(success=True, message="interaction tracked")


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

