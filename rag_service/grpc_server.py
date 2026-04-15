import logging
from concurrent import futures
from typing import Optional

import grpc

from proto import rag_pb2, rag_pb2_grpc

from .config import settings
from .rag_engine import rag_engine

logger = logging.getLogger(__name__)


class RagServicer(rag_pb2_grpc.RagServiceServicer):
    """Shared gRPC API consumed by other microservices (e.g., Social)."""

    async def TrackInteraction(self, request: rag_pb2.TrackInteractionRequest, context):
        # Keep this non-blocking for callers; interaction persistence can be expanded later.
        return rag_pb2.TrackInteractionResponse(success=True, message="interaction received")

    async def IndexBooks(self, request: rag_pb2.IndexBooksRequest, context):
        indexed = 0
        failed = 0

        for book in request.books:
            payload = {
                "work_id": book.book_id,
                "title": book.title,
                "primary_author": book.authors,
                "authors": [a.strip() for a in book.authors.split(",") if a.strip()],
                "description": book.description,
                "genres": list(book.categories),
                "rag_document": (
                    f"Title: {book.title}\n"
                    f"Author(s): {book.authors}\n"
                    f"Description: {book.description}\n"
                    f"Categories: {', '.join(book.categories)}\n"
                    f"Author style: {book.author_style}"
                ),
                "content_analysis": {"key_themes": []},
            }

            if await rag_engine.index_book(payload):
                indexed += 1
            else:
                failed += 1

        return rag_pb2.IndexBooksResponse(
            indexed=indexed,
            failed=failed,
            message="indexed" if failed == 0 else "indexed with partial failures",
        )


class GRPCServer:
    """gRPC server manager."""

    def __init__(self):
        self.server: Optional[grpc.aio.Server] = None
        self.port = settings.GRPC_PORT
        self.host = settings.GRPC_HOST

    async def start(self):
        self.server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
        rag_pb2_grpc.add_RagServiceServicer_to_server(RagServicer(), self.server)

        address = f"{self.host}:{self.port}"
        self.server.add_insecure_port(address)

        await self.server.start()
        logger.info("gRPC server started on %s", address)

    async def stop(self):
        if self.server:
            await self.server.stop(5)
            logger.info("gRPC server stopped")


grpc_server = GRPCServer()
