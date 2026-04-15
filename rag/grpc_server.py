import logging
from concurrent import futures
from typing import Optional

import grpc

from proto import rag_pb2, rag_pb2_grpc

from .config import settings
from rag import embedding_generator
from rag.engine import rag_engine
from rag import vector_store

logger = logging.getLogger(__name__)


def _as_candidate(item: dict) -> rag_pb2.RetrievalCandidate:
    author = item.get("author") or ""
    authors = list(item.get("authors") or [])
    if not authors and author:
        authors = [author]
    return rag_pb2.RetrievalCandidate(
        book_id=str(item.get("work_id") or item.get("book_id") or ""),
        title=str(item.get("title") or ""),
        authors=authors,
        genres=list(item.get("genres") or []),
        themes=list(item.get("themes") or []),
        score=float(item.get("score", 0.0)),
    )


class RagServicer(rag_pb2_grpc.RagServiceServicer):
    """Retrieval gRPC API consumed by Recommendation and other services."""

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

    async def GetSimilarBooks(self, request: rag_pb2.GetSimilarBooksRequest, context):
        try:
            top_k = request.top_k or 5
            results = await rag_engine.recommend_similar(request.book_id, top_k=top_k)
            return rag_pb2.GetSimilarBooksResponse(candidates=[_as_candidate(item) for item in results])
        except Exception as exc:
            logger.error("GetSimilarBooks failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return rag_pb2.GetSimilarBooksResponse()

    async def SemanticSearch(self, request: rag_pb2.SemanticSearchRequest, context):
        try:
            filters = {}
            if request.genre:
                filters["genres"] = [request.genre]
            if request.author:
                filters["author"] = request.author

            results = await rag_engine.search(
                query=request.query,
                top_k=request.top_k or 5,
                entity_type=request.entity_type or None,
                filters=filters if filters else None,
            )
            return rag_pb2.SemanticSearchResponse(candidates=[_as_candidate(item) for item in results])
        except Exception as exc:
            logger.error("SemanticSearch failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return rag_pb2.SemanticSearchResponse()

    async def GetBookEmbedding(self, request: rag_pb2.GetBookEmbeddingRequest, context):
        try:
            doc = await vector_store.get_by_id(f"book:{request.book_id}")
            if not doc or not doc.get("text"):
                return rag_pb2.GetBookEmbeddingResponse(found=False, vector=[])

            vector = await embedding_generator.generate_single(doc["text"])
            return rag_pb2.GetBookEmbeddingResponse(found=True, vector=vector)
        except Exception as exc:
            logger.error("GetBookEmbedding failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return rag_pb2.GetBookEmbeddingResponse(found=False, vector=[])


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
