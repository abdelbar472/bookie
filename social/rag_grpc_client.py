import logging

import grpc

from proto import rag_pb2, rag_pb2_grpc
from .config import settings

logger = logging.getLogger(__name__)

_channel: grpc.aio.Channel | None = None
_stub: rag_pb2_grpc.RagServiceStub | None = None


def _get_rag_stub() -> rag_pb2_grpc.RagServiceStub:
    global _channel, _stub
    if _stub is None:
        host = settings.RAG_GRPC_HOST
        if host in ("localhost", "0.0.0.0"):
            host = "127.0.0.1"
        addr = f"{host}:{settings.RAG_GRPC_PORT}"
        _channel = grpc.aio.insecure_channel(addr)
        _stub = rag_pb2_grpc.RagServiceStub(_channel)
        logger.info("Social->RAG gRPC channel opened at %s", addr)
    return _stub


async def close_rag_channel() -> None:
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None


async def track_interaction(
    *,
    user_id: int,
    book_id: str,
    qdrant_id: str,
    interaction_type: str,
    value: float = 0.0,
) -> bool:
    stub = _get_rag_stub()
    try:
        resp = await stub.TrackInteraction(
            rag_pb2.TrackInteractionRequest(
                user_id=int(user_id),
                book_id=book_id,
                qdrant_id=qdrant_id,
                interaction_type=interaction_type,
                value=float(value),
            )
        )
        return bool(resp.success)
    except grpc.aio.AioRpcError as exc:
        logger.warning("RAG TrackInteraction failed: %s", exc)
        return False

