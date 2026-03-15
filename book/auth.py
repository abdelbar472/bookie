"""
Book service – gRPC auth dependency.

Validates the Bearer token by calling the Auth service over gRPC,
then returns the authenticated user_id (int).
"""
import logging

import grpc
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from proto import auth_pb2, auth_pb2_grpc
from .config import settings

logger = logging.getLogger(__name__)
_security = HTTPBearer(auto_error=False)

_channel: grpc.aio.Channel | None = None
_stub: auth_pb2_grpc.AuthServiceStub | None = None


def _get_auth_stub() -> auth_pb2_grpc.AuthServiceStub:
    global _channel, _stub
    if _stub is None:
        host = settings.AUTH_GRPC_HOST
        if host in ("localhost", "0.0.0.0"):
            host = "127.0.0.1"
        addr = f"{host}:{settings.AUTH_GRPC_PORT}"
        _channel = grpc.aio.insecure_channel(addr)
        _stub = auth_pb2_grpc.AuthServiceStub(_channel)
        logger.info("Book→Auth gRPC channel opened at %s", addr)
    return _stub


async def close_auth_channel():
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> int:
    """
    FastAPI dependency.
    1. Extracts the Bearer token from the Authorization header.
    2. Calls Auth service via gRPC → ValidateToken.
    3. Returns the authenticated user_id (int).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated – provide a Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        stub = _get_auth_stub()
        response = await stub.ValidateToken(
            auth_pb2.ValidateTokenRequest(access_token=credentials.credentials)
        )
    except grpc.RpcError as exc:
        logger.error("gRPC error during token validation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service unavailable",
        )

    if not response.valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalid: {response.error}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return int(response.user.id)

