"""
Book gRPC server.

Exposes BookService to internal micro-services so they can:
  - GetBook          – fetch a book by ISBN
  - GetBooksByAuthor – list books by an author
  - SearchBooks      – search books by title
  - GetAuthor        – fetch an author by id
  - GetPublisher     – fetch a publisher by name
"""
import sys
import os
import logging

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from proto import book_pb2, book_pb2_grpc          # noqa: E402
from .services import (                             # noqa: E402
    get_book_by_isbn,
    get_author_by_id,
    get_author_books,
    get_publisher_by_name,
    search_books,
    enrich_book,
)
from .database import AsyncSessionLocal            # noqa: E402

logger = logging.getLogger(__name__)


class BookServicer(book_pb2_grpc.BookServiceServicer):

    # ── GetBook ────────────────────────────────────────────────────────────
    async def GetBook(self, request, context):
        async with AsyncSessionLocal() as session:
            book = await get_book_by_isbn(session, request.isbn)
            if book is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Book '{request.isbn}' not found")
                return book_pb2.BookPayload()
            enriched = await enrich_book(session, book)
        return book_pb2.BookPayload(
            isbn=enriched["isbn"],
            title=enriched["title"],
            year=enriched["year"],
            author_id=enriched["author_id"],
            author_name=enriched["author_name"] or "",
            publisher=enriched["publisher_name"] or "",
        )

    # ── GetBooksByAuthor ───────────────────────────────────────────────────
    async def GetBooksByAuthor(self, request, context):
        async with AsyncSessionLocal() as session:
            books, total = await get_author_books(
                session,
                request.author_id,
                skip=request.skip,
                limit=request.limit or 20,
            )
            payloads = []
            for book in books:
                enriched = await enrich_book(session, book)
                payloads.append(book_pb2.BookPayload(
                    isbn=enriched["isbn"],
                    title=enriched["title"],
                    year=enriched["year"],
                    author_id=enriched["author_id"],
                    author_name=enriched["author_name"] or "",
                    publisher=enriched["publisher_name"] or "",
                ))
        return book_pb2.BookListResponse(books=payloads, total=total)

    # ── SearchBooks ────────────────────────────────────────────────────────
    async def SearchBooks(self, request, context):
        async with AsyncSessionLocal() as session:
            books, total = await search_books(
                session,
                request.query,
                skip=request.skip,
                limit=request.limit or 20,
            )
            payloads = []
            for book in books:
                enriched = await enrich_book(session, book)
                payloads.append(book_pb2.BookPayload(
                    isbn=enriched["isbn"],
                    title=enriched["title"],
                    year=enriched["year"],
                    author_id=enriched["author_id"],
                    author_name=enriched["author_name"] or "",
                    publisher=enriched["publisher_name"] or "",
                ))
        return book_pb2.BookListResponse(books=payloads, total=total)

    # ── GetAuthor ──────────────────────────────────────────────────────────
    async def GetAuthor(self, request, context):
        async with AsyncSessionLocal() as session:
            author = await get_author_by_id(session, request.author_id)
            if author is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Author {request.author_id} not found")
                return book_pb2.AuthorPayload()
        return book_pb2.AuthorPayload(
            id=author.id,
            name=author.name,
            country=author.country or "",
            year_born=author.year_born or 0,
            year_died=author.year_died or 0,
            type_of_writer=author.type_of_writer or "",
        )

    # ── GetPublisher ───────────────────────────────────────────────────────
    async def GetPublisher(self, request, context):
        async with AsyncSessionLocal() as session:
            pub = await get_publisher_by_name(session, request.name)
            if pub is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Publisher '{request.name}' not found")
                return book_pb2.PublisherPayload()
        return book_pb2.PublisherPayload(
            name=pub.name,
            location=pub.location or "",
            year_founded=pub.year_founded or 0,
        )


async def serve_grpc(host: str = "127.0.0.1", port: int = 50054):
    server = grpc.aio.server()
    book_pb2_grpc.add_BookServiceServicer_to_server(BookServicer(), server)
    listen_addr = f"{host}:{port}"
    bound = server.add_insecure_port(listen_addr)
    if bound == 0:
        raise RuntimeError(
            f"gRPC failed to bind on {listen_addr}. Is port {port} already in use?"
        )
    await server.start()
    logger.info("Book gRPC server listening on %s", listen_addr)
    return server

