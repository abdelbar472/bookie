"""Social gRPC server."""

import logging
import os
import sys

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import proto.social_pb2 as social_pb2  # noqa: E402
import proto.social_pb2_grpc as social_pb2_grpc  # noqa: E402
from .database import AsyncSessionLocal  # noqa: E402
from .services import get_book_social_stats  # noqa: E402

logger = logging.getLogger(__name__)


class SocialServicer(social_pb2_grpc.SocialServiceServicer):
    async def GetBookStats(self, request, context):
        async with AsyncSessionLocal() as session:
            stats = await get_book_social_stats(session, request.isbn)

        avg_rating = stats.get("avg_rating")
        return social_pb2.BookSocialStatsPayload(
            isbn=stats.get("isbn", request.isbn),
            likes_count=int(stats.get("likes_count", 0)),
            ratings_count=int(stats.get("ratings_count", 0)),
            avg_rating=float(avg_rating) if avg_rating is not None else 0.0,
            has_avg_rating=avg_rating is not None,
        )

    async def Health(self, request, context):
        return social_pb2.HealthResponse(status="healthy", service="social-service")


async def serve_grpc(host: str = "127.0.0.1", port: int = 50054):
    server = grpc.aio.server()
    social_pb2_grpc.add_SocialServiceServicer_to_server(SocialServicer(), server)
    listen_addr = f"{host}:{port}"
    bound_port = server.add_insecure_port(listen_addr)
    if bound_port == 0:
        raise RuntimeError(f"gRPC failed to bind on {listen_addr}. Is port {port} already in use?")
    await server.start()
    logger.info("Social gRPC server listening on %s", listen_addr)
    return server
