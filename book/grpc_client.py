"""
gRPC client for the Book service.

Used by other micro-services (e.g. User) to query book data
without going through HTTP.
"""
import sys
import os
import logging

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from proto import book_pb2, book_pb2_grpc  # noqa: E402
from .config import settings               # noqa: E402

logger = logging.getLogger(__name__)

_channel: grpc.aio.Channel | None = None
_stub: book_pb2_grpc.BookServiceStub | None = None


def _get_book_stub() -> book_pb2_grpc.BookServiceStub:
    global _channel, _stub
    if _stub is None:
        host = settings.BOOK_GRPC_HOST
        if host in ("localhost", "0.0.0.0"):
            host = "127.0.0.1"
        addr = f"{host}:{settings.GRPC_PORT}"
        _channel = grpc.aio.insecure_channel(addr)
        _stub = book_pb2_grpc.BookServiceStub(_channel)
        logger.info("Book gRPC client connected at %s", addr)
    return _stub


async def close_book_channel():
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None


async def get_book(isbn: str) -> book_pb2.BookPayload:
    return await _get_book_stub().GetBook(book_pb2.GetBookRequest(isbn=isbn))


async def get_books_by_author(
    author_id: int, skip: int = 0, limit: int = 20
) -> book_pb2.BookListResponse:
    return await _get_book_stub().GetBooksByAuthor(
        book_pb2.GetBooksByAuthorRequest(author_id=author_id, skip=skip, limit=limit)
    )


async def search_books(
    query: str, skip: int = 0, limit: int = 20
) -> book_pb2.BookListResponse:
    return await _get_book_stub().SearchBooks(
        book_pb2.SearchBooksRequest(query=query, skip=skip, limit=limit)
    )


async def get_author(author_id: int) -> book_pb2.AuthorPayload:
    return await _get_book_stub().GetAuthor(book_pb2.GetAuthorRequest(author_id=author_id))


async def get_publisher(name: str) -> book_pb2.PublisherPayload:
    return await _get_book_stub().GetPublisher(book_pb2.GetPublisherRequest(name=name))

