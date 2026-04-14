import logging
from concurrent import futures
from typing import Optional

import grpc

from .config import settings
from .rag_engine import rag_engine
from .services import RecommendationService, SearchService
from .proto import rag_pb2, rag_pb2_grpc

logger = logging.getLogger(__name__)


class RAGServicer(rag_pb2_grpc.RAGServiceServicer):
    """gRPC servicer for RAG operations."""

    @staticmethod
    def _to_book_payload(book_msg: rag_pb2.Book) -> dict:
        return {
            "work_id": book_msg.work_id,
            "title": book_msg.title,
            "primary_author": book_msg.primary_author,
            "rag_document": book_msg.rag_document,
            "description": book_msg.description,
            "genres": list(book_msg.genres),
            "content_analysis": {
                "key_themes": list(book_msg.themes)
            } if book_msg.themes else {},
        }

    async def IndexBook(self, request: rag_pb2.IndexBookRequest, context):
        try:
            success = await rag_engine.index_book(self._to_book_payload(request.book))
            return rag_pb2.IndexResponse(
                success=success,
                message="Book indexed" if success else "Failed to index book",
            )
        except Exception as exc:
            logger.error("gRPC IndexBook failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return rag_pb2.IndexResponse(success=False, message=str(exc))

    async def IndexBatch(self, request: rag_pb2.BatchIndexRequest, context):
        try:
            indexed_count = 0
            for book_msg in request.books:
                if await rag_engine.index_book(self._to_book_payload(book_msg)):
                    indexed_count += 1

            return rag_pb2.BatchIndexResponse(
                success=indexed_count > 0,
                indexed_count=indexed_count,
                failed_count=len(request.books) - indexed_count,
            )
        except Exception as exc:
            logger.error("gRPC IndexBatch failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return rag_pb2.BatchIndexResponse(success=False, indexed_count=0, failed_count=len(request.books))

    async def Search(self, request: rag_pb2.SearchRequest, context):
        try:
            result = await SearchService.semantic_search(
                query=request.query,
                top_k=request.top_k or 5,
                entity_type=request.entity_type or None,
                genre=request.genre or None,
            )

            response = rag_pb2.SearchResponse(total_count=len(result.get("results", [])))
            for item in result.get("results", []):
                response.results.append(
                    rag_pb2.SearchResult(
                        work_id=item.get("work_id", ""),
                        title=item.get("title", ""),
                        author=item.get("author", ""),
                        score=float(item.get("score", 0.0)),
                        text=(item.get("text") or "")[:500],
                        entity_type=item.get("entity_type", "book"),
                    )
                )
            return response
        except Exception as exc:
            logger.error("gRPC Search failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return rag_pb2.SearchResponse(results=[], total_count=0)

    async def GetRecommendations(self, request: rag_pb2.RecommendRequest, context):
        try:
            result = await RecommendationService.get_recommendations(
                user_history=list(request.work_ids),
                top_k=request.top_k or 5,
                diversify=request.diversify,
            )
            response = rag_pb2.RecommendResponse()
            for item in result.get("recommendations", []):
                work_id = item.get("work_id")
                if work_id:
                    response.work_ids.append(work_id)
                    response.details.append(
                        rag_pb2.SearchResult(
                            work_id=work_id,
                            title=item.get("title", ""),
                            author=item.get("author", ""),
                            score=float(item.get("score", 0.0)),
                            text=(item.get("text") or "")[:500],
                            entity_type=item.get("entity_type", "book"),
                        )
                    )
            return response
        except Exception as exc:
            logger.error("gRPC GetRecommendations failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return rag_pb2.RecommendResponse()

    async def HealthCheck(self, request: rag_pb2.HealthRequest, context):
        from .vector_store import vector_store

        try:
            count = await vector_store.count()
            return rag_pb2.HealthResponse(
                status="healthy",
                indexed_documents=count,
                version=settings.VERSION,
            )
        except Exception as exc:
            logger.error("gRPC HealthCheck failed: %s", exc)
            return rag_pb2.HealthResponse(
                status="unhealthy",
                indexed_documents=0,
                version=settings.VERSION,
            )


class GRPCServer:
    """gRPC server manager."""

    def __init__(self):
        self.server: Optional[grpc.aio.Server] = None
        self.port = settings.GRPC_PORT
        self.host = settings.GRPC_HOST

    async def start(self):
        self.server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
        rag_pb2_grpc.add_RAGServiceServicer_to_server(RAGServicer(), self.server)

        address = f"{self.host}:{self.port}"
        self.server.add_insecure_port(address)

        await self.server.start()
        logger.info("gRPC server started on %s", address)

    async def stop(self):
        if self.server:
            await self.server.stop(5)
            logger.info("gRPC server stopped")


grpc_server = GRPCServer()

