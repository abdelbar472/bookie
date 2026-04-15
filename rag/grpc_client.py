import asyncio
import logging
from typing import Optional

import grpc

from proto import book_v3_pb2, book_v3_pb2_grpc

from .config import settings

logger = logging.getLogger(__name__)


class BookServiceGRPCClient:
    """gRPC client to communicate with Book Service V3."""

    def __init__(self):
        self.host = settings.BOOK_V3_GRPC_HOST
        self.port = settings.BOOK_V3_GRPC_PORT
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[book_v3_pb2_grpc.BookV3ServiceStub] = None

    async def connect(self):
        try:
            target = f"{self.host}:{self.port}"
            self.channel = grpc.aio.insecure_channel(target)
            await asyncio.wait_for(self.channel.channel_ready(), timeout=5)
            self.stub = book_v3_pb2_grpc.BookV3ServiceStub(self.channel)
            logger.info("Connected to Book Service gRPC at %s", target)
            return True
        except Exception as exc:
            logger.warning("Could not connect to Book Service gRPC: %s", exc)
            self.channel = None
            return False

    async def get_book(self, work_id: str):
        if not self.stub:
            return None

        try:
            request = book_v3_pb2.GetBookByWorkIdRequest(work_id=work_id)
            return await self.stub.GetBookByWorkId(request)
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error("gRPC GetBook failed: %s", exc)
            return None
        except Exception as exc:
            logger.error("gRPC GetBook failed: %s", exc)
            return None

    async def list_books(self, limit: int = 100, skip: int = 0):
        if not self.stub:
            return []

        try:
            request = book_v3_pb2.ListBooksRequest(limit=limit, skip=skip)
            response = await self.stub.ListBooks(request)
            return list(response.books)
        except Exception as exc:
            logger.error("gRPC ListBooks failed: %s", exc)
            return []

    async def search_books(self, query: str, limit: int = 20, skip: int = 0):
        if not self.stub:
            return []

        try:
            request = book_v3_pb2.SearchBooksRequest(query=query, limit=limit, skip=skip)
            response = await self.stub.SearchBooks(request)
            return list(response.books)
        except Exception as exc:
            logger.error("gRPC SearchBooks failed: %s", exc)
            return []

    async def close(self):
        if self.channel:
            await self.channel.close()
            self.stub = None
            logger.info("Book Service gRPC connection closed")


book_service_client = BookServiceGRPCClient()