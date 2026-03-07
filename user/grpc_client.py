"""
gRPC client for the User service.

Calls the Auth service over gRPC to:
  - ValidateToken  – verify a JWT
  - RefreshToken   – rotate tokens
  - GetUser        – fetch user by id
"""
import sys
import os
import logging

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from proto import auth_pb2, auth_pb2_grpc   # noqa: E402
from .config import settings                 # noqa: E402

logger = logging.getLogger(__name__)

_channel: grpc.aio.Channel | None = None
_stub: auth_pb2_grpc.AuthServiceStub | None = None


def get_auth_stub() -> auth_pb2_grpc.AuthServiceStub:
    global _channel, _stub
    if _stub is None:
        host = settings.AUTH_GRPC_HOST
        # resolve "localhost" → "127.0.0.1" to avoid IPv6 resolution issues on Windows
        if host == "localhost":
            host = "127.0.0.1"
        addr = f"{host}:{settings.AUTH_GRPC_PORT}"
        _channel = grpc.aio.insecure_channel(addr)
        _stub = auth_pb2_grpc.AuthServiceStub(_channel)
        logger.info("gRPC channel opened → Auth service at %s", addr)
    return _stub


async def close_grpc_channel():
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None


async def validate_token(access_token: str) -> auth_pb2.ValidateTokenResponse:
    stub = get_auth_stub()
    return await stub.ValidateToken(auth_pb2.ValidateTokenRequest(access_token=access_token))


async def refresh_token(refresh_token: str) -> auth_pb2.RefreshTokenResponse:
    stub = get_auth_stub()
    return await stub.RefreshToken(auth_pb2.RefreshTokenRequest(refresh_token=refresh_token))


async def get_user(user_id: int) -> auth_pb2.UserPayload:
    stub = get_auth_stub()
    return await stub.GetUser(auth_pb2.GetUserRequest(user_id=user_id))


async def get_user_by_username(username: str) -> auth_pb2.UserPayload:
    stub = get_auth_stub()
    return await stub.GetUserByUsername(auth_pb2.GetUserByUsernameRequest(username=username))


