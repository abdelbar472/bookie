import asyncio
import logging
from typing import Optional

import grpc

from .config import settings

logger = logging.getLogger(__name__)


class BookServiceGRPCClient:
    """gRPC client to communicate with Book Service V3."""

    def __init__(self):
        self.host = settings.BOOK_SERVICE_GRPC_HOST
        self.port = settings.BOOK_SERVICE_GRPC_PORT
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None

    async def connect(self):
        try:
            target = f"{self.host}:{self.port}"
            self.channel = grpc.aio.insecure_channel(target)
            await asyncio.wait_for(self.channel.channel_ready(), timeout=5)

            # TODO: initialize generated protobuf stub when book service proto is available.
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
            # request = book_pb2.GetBookRequest(work_id=work_id)
            # response = await self.stub.GetBook(request)
            # return response
            return None
        except Exception as exc:
            logger.error("gRPC GetBook failed: %s", exc)
            return None

    async def list_books(self, limit: int = 100):
        if not self.stub:
            return []

        try:
            # request = book_pb2.ListBooksRequest(limit=limit)
            # response = await self.stub.ListBooks(request)
            # return list(response.books)
            return []
        except Exception as exc:
            logger.error("gRPC ListBooks failed: %s", exc)
            return []

    async def close(self):
        if self.channel:
            await self.channel.close()
            logger.info("Book Service gRPC connection closed")


book_service_client = BookServiceGRPCClient()