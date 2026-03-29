import grpc
import logging
from concurrent import futures

from proto import recommendation_pb2, recommendation_pb2_grpc
from .config import settings
from .vector_store import index_books

logger = logging.getLogger(__name__)


class RecommendationServicer(recommendation_pb2_grpc.RecommendationServiceServicer):

    async def IndexBooks(self, request, context):
        """Receive books from Book Service, generate embeddings, store in Qdrant"""
        books = []
        for book in request.books:
            books.append({
                "book_id": book.book_id,
                "title": book.title,
                "authors": list(book.authors),
                "author_ids": list(book.author_ids),
                "description": book.description,
                "categories": list(book.categories),
                "thumbnail": book.thumbnail,
                "published_date": book.published_date,
                "language": book.language,
                "average_rating": book.average_rating,
                "ratings_count": book.ratings_count,
            })

        await index_books(books)

        return recommendation_pb2.IndexBooksResponse(indexed=len(books))


async def serve_grpc():
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    recommendation_pb2_grpc.add_RecommendationServiceServicer_to_server(
        RecommendationServicer(), server
    )
    server.add_insecure_port(f"[::]:{settings.GRPC_PORT}")
    await server.start()
    logger.info(f"gRPC server on port {settings.GRPC_PORT}")
    return server