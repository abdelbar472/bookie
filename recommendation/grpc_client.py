"""gRPC client for rag retrieval APIs."""

import logging
from typing import Optional

import grpc

from proto import rag_pb2, rag_pb2_grpc

from .config import settings

logger = logging.getLogger(__name__)

_channel: Optional[grpc.aio.Channel] = None
_stub: Optional[rag_pb2_grpc.RagServiceStub] = None


def _get_stub() -> rag_pb2_grpc.RagServiceStub:
    global _channel, _stub
    if _stub is None:
        host = settings.RAG_GRPC_HOST
        if host in ("localhost", "0.0.0.0"):
            host = "127.0.0.1"
        address = f"{host}:{settings.RAG_GRPC_PORT}"
        _channel = grpc.aio.insecure_channel(address)
        _stub = rag_pb2_grpc.RagServiceStub(_channel)
        logger.info("Recommendation -> RAG gRPC channel opened at %s", address)
    return _stub


async def close_rag_channel() -> None:
    global _channel, _stub
    if _channel:
        await _channel.close()
    _channel = None
    _stub = None


async def get_similar_books(book_id: str, top_k: int = 3) -> list[dict]:
    request = rag_pb2.GetSimilarBooksRequest(book_id=book_id, top_k=top_k)
    response = await _get_stub().GetSimilarBooks(request)

    items: list[dict] = []
    for cand in response.candidates:
        items.append(
            {
                "work_id": cand.book_id,
                "book_id": cand.book_id,
                "title": cand.title,
                "authors": list(cand.authors),
                "author": cand.authors[0] if cand.authors else "",
                "genres": list(cand.genres),
                "themes": list(cand.themes),
                "score": float(cand.score),
            }
        )
    return items

