"""gRPC server for Book Service V3."""
import logging
from concurrent import futures
from typing import Optional

import grpc

from proto import book_v3_pb2, book_v3_pb2_grpc

from .config import settings
from .services import BookService

logger = logging.getLogger(__name__)


class BookV3Servicer(book_v3_pb2_grpc.BookV3ServiceServicer):
    @staticmethod
    def _to_payload(book) -> book_v3_pb2.BookV3Payload:
        themes = []
        if getattr(book, "content_analysis", None):
            themes = list(book.content_analysis.key_themes)

        return book_v3_pb2.BookV3Payload(
            work_id=book.work_id,
            title=book.title,
            primary_author=book.primary_author,
            authors=list(book.authors),
            description=book.description or "",
            genres=list(book.genres),
            themes=themes,
            rag_document=book.to_rag_text(),
        )

    async def GetBookByWorkId(self, request, context):
        book = await BookService.get_book_by_id(request.work_id)
        if not book:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Book not found: {request.work_id}")
            return book_v3_pb2.BookV3Payload()
        return self._to_payload(book)

    async def ListBooks(self, request, context):
        limit = request.limit or 100
        books = await BookService.list_books(limit=limit, skip=request.skip)
        payloads = [self._to_payload(book) for book in books]
        return book_v3_pb2.BookV3ListResponse(books=payloads, total=len(payloads))

    async def SearchBooks(self, request, context):
        limit = request.limit or 20
        result = await BookService.search_books(request.query, limit=limit, skip_cache=False)
        payloads = [self._to_payload(book) for book in result.results]
        return book_v3_pb2.BookV3ListResponse(books=payloads, total=result.count)


class GRPCServer:
    def __init__(self):
        self.server: Optional[grpc.aio.Server] = None

    async def start(self) -> None:
        self.server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
        book_v3_pb2_grpc.add_BookV3ServiceServicer_to_server(BookV3Servicer(), self.server)

        address = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
        self.server.add_insecure_port(address)
        await self.server.start()
        logger.info("Book V3 gRPC server started on %s", address)

    async def stop(self) -> None:
        if self.server:
            await self.server.stop(5)
            logger.info("Book V3 gRPC server stopped")


grpc_server = GRPCServer()

