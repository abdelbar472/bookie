"""User gRPC server."""

import logging
import os
import sys

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import proto.user_pb2 as user_pb2  # noqa: E402
import proto.user_pb2_grpc as user_pb2_grpc  # noqa: E402
from .database import AsyncSessionLocal  # noqa: E402
from .services import get_or_create_profile  # noqa: E402

logger = logging.getLogger(__name__)


class UserServicer(user_pb2_grpc.UserServiceServicer):
    async def GetProfile(self, request, context):
        async with AsyncSessionLocal() as session:
            profile = await get_or_create_profile(session, request.user_id)

        return user_pb2.UserProfilePayload(
            user_id=profile.user_id,
            bio=profile.bio or "",
            avatar_url=profile.profile_picture or "",
            location=profile.location or "",
            website=profile.website or "",
            created_at=profile.created_at.isoformat() if profile.created_at else "",
            updated_at=profile.updated_at.isoformat() if profile.updated_at else "",
        )

    async def Health(self, request, context):
        return user_pb2.HealthResponse(status="healthy", service="user-service")


async def serve_grpc(host: str = "127.0.0.1", port: int = 50052):
    server = grpc.aio.server()
    user_pb2_grpc.add_UserServiceServicer_to_server(UserServicer(), server)
    listen_addr = f"{host}:{port}"
    bound_port = server.add_insecure_port(listen_addr)
    if bound_port == 0:
        raise RuntimeError(f"gRPC failed to bind on {listen_addr}. Is port {port} already in use?")
    await server.start()
    logger.info("User gRPC server listening on %s", listen_addr)
    return server
