import grpc
import logging
from typing import List, Dict

from proto import recommendation_pb2, recommendation_pb2_grpc
from .config import settings

logger = logging.getLogger(__name__)
_channel = None
_stub = None


def get_stub():
    global _channel, _stub
    if _stub is None:
        _channel = grpc.aio.insecure_channel(
            f"{settings.RECOMMENDATION_GRPC_HOST}:{settings.RECOMMENDATION_GRPC_PORT}"
        )
        _stub = recommendation_pb2_grpc.RecommendationServiceStub(_channel)
    return _stub


async def push_books_to_recommendation(books: List[Dict]):
    """Stream raw books to recommendation service - NO EMBEDDINGS HERE"""
    if not books:
        return 0

    request_books = []
    for book in books:
        request_books.append(recommendation_pb2.BookPayload(
            book_id=book["book_id"],
            title=book["title"],
            authors=book["authors"],
            author_ids=book["author_ids"],
            description=book.get("description") or "",
            categories=book.get("categories", []),
            thumbnail=book.get("thumbnail") or "",
            published_date=book.get("published_date") or "",
            language=book.get("language") or "",
            average_rating=book.get("average_rating") or 0.0,
            ratings_count=book.get("ratings_count") or 0,
        ))

    try:
        stub = get_stub()
        response = await stub.IndexBooks(
            recommendation_pb2.IndexBooksRequest(books=request_books)
        )
        logger.info(f"Pushed {response.indexed} books to recommendation service")
        return response.indexed
    except grpc.RpcError as e:
        logger.error(f"Failed to push books: {e}")
        return 0