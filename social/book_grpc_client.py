import logging
import grpc
from typing import Optional

# Generated proto files
from proto import book_v4_pb2 as book_pb2
from proto import book_v4_pb2_grpc as book_pb2_grpc

from .config import settings

logger = logging.getLogger(__name__)

# Global variables
book_channel: Optional[grpc.aio.Channel] = None
book_stub: Optional[book_pb2_grpc.BookServiceStub] = None


async def init_book_channel():
    """Initialize gRPC channel to Book service"""
    global book_channel, book_stub

    try:
        address = f"{settings.BOOK_GRPC_HOST}:{settings.BOOK_GRPC_PORT}"
        book_channel = grpc.aio.insecure_channel(address)
        book_stub = book_pb2_grpc.BookServiceStub(book_channel)
        logger.info(f"✅ Connected to Book Service gRPC at {address}")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Book Service: {e}")
        raise


async def close_book_channel():
    """Close gRPC channel"""
    global book_channel
    if book_channel:
        await book_channel.close()
        book_channel = None
        logger.info("Book gRPC channel closed")


async def assert_book_exists(isbn: str) -> None:
    """Check if book exists via gRPC - raises exception if not found"""
    global book_stub

    if book_stub is None:
        await init_book_channel()

    try:
        response = await book_stub.GetBook(
            book_pb2.GetBookRequest(isbn=isbn)
        )

        if not response.HasField("book") or not response.book.isbn:
            raise ValueError(f"Book with ISBN {isbn} not found")

        logger.debug(f"Book verified: {isbn} - {response.book.title}")

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise ValueError(f"Book with ISBN {isbn} not found")
        else:
            logger.error(f"gRPC error checking book {isbn}: {e.details()}")
            raise
    except Exception as e:
        logger.error(f"Unexpected error checking book {isbn}: {e}")
        raise

async def get_book_details(isbn: str) -> dict:
    """Get book details via gRPC"""
    global book_stub

    if book_stub is None:
        await init_book_channel()

    try:
        response = await book_stub.GetBook(
            book_pb2.GetBookRequest(isbn=isbn)
        )

        if not response.HasField("book") or not response.book.isbn:
            raise ValueError(f"Book with ISBN {isbn} not found")

        return {
            "isbn": response.book.isbn,
            "title": response.book.title,
            "author": response.book.author,
            "published_year": response.book.published_year,
            "genre": response.book.genre,
        }

    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise ValueError(f"Book with ISBN {isbn} not found")
        else:
            logger.error(f"gRPC error getting book {isbn}: {e.details()}")
            raise
    except Exception as e:
        logger.error(f"Unexpected error getting book {isbn}: {e}")
        raise
