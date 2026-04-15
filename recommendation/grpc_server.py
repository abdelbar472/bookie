"""gRPC server for recommendation service."""

import logging
from concurrent import futures
from typing import Optional

import grpc

from proto import recommendation_pb2, recommendation_pb2_grpc

from .config import settings
from .service import RecommendationService

logger = logging.getLogger(__name__)


class RecommendationServicer(recommendation_pb2_grpc.RecommendationServiceServicer):
    async def GetRecommendations(self, request, context):
        try:
            result = await RecommendationService.get_recommendations(
                user_id=request.user_id,
                history_book_ids=list(request.history_book_ids),
                top_k=request.limit or 10,
                diversify=bool(request.diversify),
                current_book_id=request.current_book_id,
            )

            recs = []
            for item in result.get("recommendations", []):
                recs.append(
                    recommendation_pb2.BookRecommendation(
                        book_id=str(item.get("work_id") or item.get("book_id") or ""),
                        title=str(item.get("title") or ""),
                        authors=list(item.get("authors") or ([item.get("author")] if item.get("author") else [])),
                        score=float(item.get("score", 0.0)),
                        reason=str(item.get("reason") or "semantic-similarity"),
                    )
                )

            return recommendation_pb2.RecommendationResponse(recommendations=recs)
        except Exception as exc:
            logger.error("GetRecommendations gRPC failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return recommendation_pb2.RecommendationResponse()

    async def UpdateUserProfile(self, request, context):
        try:
            event = request.event
            result = await RecommendationService.update_user_profile(
                user_id=event.user_id,
                book_id=event.book_id,
                interaction_type=event.interaction_type,
                value=float(event.value),
            )
            return recommendation_pb2.UpdateUserProfileResponse(
                success=bool(result.get("success", False)),
                message="profile updated",
            )
        except Exception as exc:
            logger.error("UpdateUserProfile gRPC failed: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return recommendation_pb2.UpdateUserProfileResponse(success=False, message=str(exc))


class GRPCServer:
    def __init__(self):
        self.server: Optional[grpc.aio.Server] = None

    async def start(self):
        self.server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
        recommendation_pb2_grpc.add_RecommendationServiceServicer_to_server(
            RecommendationServicer(),
            self.server,
        )
        address = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
        self.server.add_insecure_port(address)
        await self.server.start()
        logger.info("Recommendation gRPC server started on %s", address)

    async def stop(self):
        if self.server:
            await self.server.stop(5)
            logger.info("Recommendation gRPC server stopped")


grpc_server = GRPCServer()
