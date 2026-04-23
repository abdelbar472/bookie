"""gRPC client for optional Book->RAG indexing notifications."""
import asyncio
import logging
from typing import Optional

import grpc

from proto import rag_pb2, rag_pb2_grpc

from .config import settings

logger = logging.getLogger(__name__)


class RAGServiceGRPCClient:
    def __init__(self):
        self.host = settings.RAG_SERVICE_GRPC_HOST
        self.port = settings.RAG_SERVICE_GRPC_PORT
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[rag_pb2_grpc.RagServiceStub] = None

    async def connect(self) -> bool:
        try:
            target = f"{self.host}:{self.port}"
            self.channel = grpc.aio.insecure_channel(target)
            await asyncio.wait_for(self.channel.channel_ready(), timeout=5)
            self.stub = rag_pb2_grpc.RagServiceStub(self.channel)
            logger.info("Connected to RAG Service gRPC at %s", target)
            return True
        except Exception as exc:
            logger.warning("Could not connect to RAG Service gRPC: %s", exc)
            self.channel = None
            self.stub = None
            return False

    @staticmethod
    def _to_proto_book(book: dict) -> rag_pb2.IndexBookPayload:
        authors = book.get("authors") or []
        categories = book.get("categories") or []
        editions = book.get("editions") or []
        language = ""
        published_date = ""
        thumbnail = ""
        if editions and isinstance(editions[0], dict):
            language = str(editions[0].get("language") or "")
            published_date = str(editions[0].get("published_date") or "")
            thumbnail = str(editions[0].get("thumbnail") or "")

        return rag_pb2.IndexBookPayload(
            book_id=str(book.get("work_id", "")),
            title=str(book.get("title", "")),
            authors=", ".join(str(a) for a in authors),
            description=str(book.get("description", "")),
            categories=[str(c) for c in categories],
            language=language,
            average_rating=0.0,
            ratings_count=0,
            published_date=published_date,
            thumbnail=thumbnail,
            source="book-service-v3",
            author_style="",
        )

    async def notify_new_book(self, book: dict) -> bool:
        if not self.stub and not await self.connect():
            return False

        try:
            payload = self._to_proto_book(book)
            request = rag_pb2.IndexBooksRequest(books=[payload])
            response = await self.stub.IndexBooks(request, timeout=10)
            if response.failed > 0:
                logger.warning("RAG rejected index for '%s': %s", book.get("title"), response.message)
            return response.indexed > 0
        except Exception as exc:
            logger.error("Failed to notify RAG: %s", exc)
            return False

    async def close(self):
        if self.channel:
            await self.channel.close()
            logger.info("RAG Service gRPC connection closed")
            self.channel = None
            self.stub = None


rag_service_client = RAGServiceGRPCClient()


async def notify_rag_indexing(book: dict) -> bool:
    return await rag_service_client.notify_new_book(book)
