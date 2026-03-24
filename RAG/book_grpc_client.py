import logging

import grpc

from proto import book_pb2, book_pb2_grpc
from .config import settings

logger = logging.getLogger(__name__)

_channel: grpc.aio.Channel | None = None
_stub: book_pb2_grpc.BookServiceStub | None = None


def _get_book_stub() -> book_pb2_grpc.BookServiceStub:
    global _channel, _stub
    if _stub is None:
        host = settings.BOOK_GRPC_HOST
        if host in ("localhost", "0.0.0.0"):
            host = "127.0.0.1"
        addr = f"{host}:{settings.BOOK_GRPC_PORT}"
        _channel = grpc.aio.insecure_channel(addr)
        _stub = book_pb2_grpc.BookServiceStub(_channel)
        logger.info("RAG->Book gRPC channel opened at %s", addr)
    return _stub


async def close_book_channel() -> None:
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None


async def get_book_details(isbn: str) -> dict | None:
    """Fetch book details from Book service by ISBN; returns None when not found/unavailable."""
    stub = _get_book_stub()
    try:
        resp = await stub.GetBook(book_pb2.GetBookRequest(isbn=isbn))
    except grpc.aio.AioRpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            return None
        logger.warning("Book gRPC fetch failed for isbn %s: %s", isbn, exc)
        return None

    return {
        "book_id": resp.isbn,
        "title": resp.title or "",
        "authors": resp.author_name or "",
        "source": "book_service_grpc",
    }

