"""
gRPC client for the Follow service.

Used by the User service to query follow relationships
without going through HTTP.
"""
import sys
import os
import logging

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from proto import follow_pb2, follow_pb2_grpc  # noqa: E402
from .config import settings                   # noqa: E402

logger = logging.getLogger(__name__)

_channel: grpc.aio.Channel | None = None
_stub: follow_pb2_grpc.FollowServiceStub | None = None


def _get_follow_stub() -> follow_pb2_grpc.FollowServiceStub:
    global _channel, _stub
    if _stub is None:
        host = settings.FOLLOW_GRPC_HOST
        if host in ("localhost", "0.0.0.0"):
            host = "127.0.0.1"
        addr = f"{host}:{settings.FOLLOW_GRPC_PORT}"
        _channel = grpc.aio.insecure_channel(addr)
        _stub = follow_pb2_grpc.FollowServiceStub(_channel)
        logger.info("User→Follow gRPC channel opened at %s", addr)
    return _stub


async def close_follow_channel():
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None


async def is_following(follower_id: int, followee_id: int) -> bool:
    stub = _get_follow_stub()
    resp = await stub.IsFollowing(
        follow_pb2.IsFollowingRequest(follower_id=follower_id, followee_id=followee_id)
    )
    return resp.following


async def get_follow_stats(user_id: int) -> follow_pb2.GetFollowStatsResponse:
    stub = _get_follow_stub()
    return await stub.GetFollowStats(
        follow_pb2.GetFollowStatsRequest(user_id=user_id)
    )


async def get_followers(
    user_id: int, skip: int = 0, limit: int = 20
) -> follow_pb2.GetFollowListResponse:
    stub = _get_follow_stub()
    return await stub.GetFollowers(
        follow_pb2.GetFollowListRequest(user_id=user_id, skip=skip, limit=limit)
    )


async def get_following(
    user_id: int, skip: int = 0, limit: int = 20
) -> follow_pb2.GetFollowListResponse:
    stub = _get_follow_stub()
    return await stub.GetFollowing(
        follow_pb2.GetFollowListRequest(user_id=user_id, skip=skip, limit=limit)
    )

