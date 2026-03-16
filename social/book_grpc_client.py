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
        logger.info("Social->Book gRPC channel opened at %s", addr)
    return _stub


async def close_book_channel() -> None:
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None


async def assert_book_exists(isbn: str) -> None:
    stub = _get_book_stub()
    try:
        await stub.GetBook(book_pb2.GetBookRequest(isbn=isbn))
    except grpc.aio.AioRpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            raise ValueError("Book not found")
        logger.error("Book gRPC check failed: %s", exc)
        raise ValueError("Book service unavailable")

