"""
Auth gRPC server.

Exposes AuthService to internal micro-services so they can:
  - ValidateToken  – verify a JWT and get the user payload
  - RefreshToken   – rotate tokens internally
  - GetUser        – fetch a user record by id
"""
import sys
import os
import logging
import asyncio

import grpc

# Make the proto package importable regardless of cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from proto import auth_pb2, auth_pb2_grpc          # noqa: E402
from .services import (                             # noqa: E402
    decode_access_token, create_access_token,
    create_refresh_token, get_refresh_token,
    revoke_refresh_token, store_refresh_token,
    get_user_by_id, get_user_by_username,
)
from .database import AsyncSessionLocal             # noqa: E402

logger = logging.getLogger(__name__)


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):
    # ── ValidateToken ──────────────────────────────────────────────────────
    async def ValidateToken(self, request, context):
        token_data = decode_access_token(request.access_token)
        if token_data is None or token_data.user_id is None:
            logger.warning("gRPC ValidateToken: invalid token")
            return auth_pb2.ValidateTokenResponse(valid=False, error="invalid or expired token")

        async with AsyncSessionLocal() as session:
            user = await get_user_by_id(session, token_data.user_id)

        if user is None or not user.is_active:
            return auth_pb2.ValidateTokenResponse(valid=False, error="user not found or inactive")

        payload = auth_pb2.UserPayload(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name or "",
            is_active=user.is_active,
            is_superuser=user.is_superuser,
        )
        logger.info("gRPC ValidateToken: OK for user %s", user.username)
        return auth_pb2.ValidateTokenResponse(valid=True, user=payload)

    # ── RefreshToken ───────────────────────────────────────────────────────
    async def RefreshToken(self, request, context):
        async with AsyncSessionLocal() as session:
            db_token = await get_refresh_token(session, request.refresh_token)
            if not db_token:
                return auth_pb2.RefreshTokenResponse(error="invalid or expired refresh token")

            user = await get_user_by_id(session, db_token.user_id)
            if not user or not user.is_active:
                return auth_pb2.RefreshTokenResponse(error="user not found or inactive")

            new_access = create_access_token({"sub": str(user.id), "username": user.username})
            new_refresh = create_refresh_token()
            await revoke_refresh_token(session, request.refresh_token)
            await store_refresh_token(session, user.id, new_refresh)

        logger.info("gRPC RefreshToken: rotated for user %s", user.username)
        return auth_pb2.RefreshTokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
        )

    # ── GetUser ────────────────────────────────────────────────────────────
    async def GetUser(self, request, context):
        async with AsyncSessionLocal() as session:
            user = await get_user_by_id(session, request.user_id)

        if user is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, "user not found")

        return auth_pb2.UserPayload(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name or "",
            is_active=user.is_active,
            is_superuser=user.is_superuser,
        )

    # ── GetUserByUsername ──────────────────────────────────────────────────
    async def GetUserByUsername(self, request, context):
        async with AsyncSessionLocal() as session:
            user = await get_user_by_username(session, request.username)

        if user is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, "user not found")

        return auth_pb2.UserPayload(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name or "",
            is_active=user.is_active,
            is_superuser=user.is_superuser,
        )


async def serve_grpc(host: str = "127.0.0.1", port: int = 50051):
    server = grpc.aio.server()
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    listen_addr = f"{host}:{port}"
    bound_port = server.add_insecure_port(listen_addr)
    if bound_port == 0:
        raise RuntimeError(
            f"gRPC failed to bind on {listen_addr}. "
            f"Is port {port} already in use?"
        )
    await server.start()
    logger.info("✅ Auth gRPC server listening on %s", listen_addr)
    return server

