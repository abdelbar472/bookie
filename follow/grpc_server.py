"""
Follow gRPC server.

Exposes FollowService to internal micro-services so they can:
  - IsFollowing    – check follower → followee relationship
  - GetFollowStats – follower / following counts for a user
  - GetFollowers   – paginated list of follower user_ids
  - GetFollowing   – paginated list of following user_ids
"""
import sys
import os
import logging

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from proto import follow_pb2, follow_pb2_grpc          # noqa: E402
from .services import (                                 # noqa: E402
    is_following,
    get_followers,
    get_following,
    get_follow_stats,
)
from .database import AsyncSessionLocal                 # noqa: E402

logger = logging.getLogger(__name__)


class FollowServicer(follow_pb2_grpc.FollowServiceServicer):

    # ── IsFollowing ────────────────────────────────────────────────────────
    async def IsFollowing(self, request, context):
        async with AsyncSessionLocal() as session:
            result = await is_following(session, request.follower_id, request.followee_id)
        return follow_pb2.IsFollowingResponse(following=result)

    # ── GetFollowStats ─────────────────────────────────────────────────────
    async def GetFollowStats(self, request, context):
        async with AsyncSessionLocal() as session:
            stats = await get_follow_stats(session, request.user_id)
        return follow_pb2.GetFollowStatsResponse(
            user_id=stats["user_id"],
            followers_count=stats["followers_count"],
            following_count=stats["following_count"],
        )

    # ── GetFollowers ───────────────────────────────────────────────────────
    async def GetFollowers(self, request, context):
        async with AsyncSessionLocal() as session:
            entries, total = await get_followers(
                session,
                request.user_id,
                skip=request.skip,
                limit=request.limit or 20,
            )
        return follow_pb2.GetFollowListResponse(
            user_ids=[e.user_id for e in entries],
            total=total,
        )

    # ── GetFollowing ───────────────────────────────────────────────────────
    async def GetFollowing(self, request, context):
        async with AsyncSessionLocal() as session:
            entries, total = await get_following(
                session,
                request.user_id,
                skip=request.skip,
                limit=request.limit or 20,
            )
        return follow_pb2.GetFollowListResponse(
            user_ids=[e.user_id for e in entries],
            total=total,
        )


async def serve_grpc(host: str = "0.0.0.0", port: int = 50052):
    server = grpc.aio.server()
    follow_pb2_grpc.add_FollowServiceServicer_to_server(FollowServicer(), server)
    listen_addr = f"{host}:{port}"
    try:
        server.add_insecure_port(listen_addr)
        await server.start()
    except Exception as exc:
        raise RuntimeError(
            f"gRPC failed to bind on {listen_addr}. "
            f"Is port {port} already in use? ({exc})"
        ) from exc
    logger.info("✅ Follow gRPC server listening on %s", listen_addr)
    return server

