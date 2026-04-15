"""gRPC client for recommendation service profile updates."""

import logging

import grpc

from proto import recommendation_pb2, recommendation_pb2_grpc

from .config import settings

logger = logging.getLogger(__name__)

_channel: grpc.aio.Channel | None = None
_stub: recommendation_pb2_grpc.RecommendationServiceStub | None = None


def _get_recommendation_stub() -> recommendation_pb2_grpc.RecommendationServiceStub:
    global _channel, _stub
    if _stub is None:
        host = settings.RECOMMENDATION_GRPC_HOST
        if host in ("localhost", "0.0.0.0"):
            host = "127.0.0.1"
        addr = f"{host}:{settings.RECOMMENDATION_GRPC_PORT}"
        _channel = grpc.aio.insecure_channel(addr)
        _stub = recommendation_pb2_grpc.RecommendationServiceStub(_channel)
        logger.info("Social->Recommendation gRPC channel opened at %s", addr)
    return _stub


async def close_recommendation_channel() -> None:
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None


async def track_interaction(
    *,
    user_id: int,
    book_id: str,
    interaction_type: str,
    value: float = 0.0,
) -> bool:
    stub = _get_recommendation_stub()
    try:
        resp = await stub.UpdateUserProfile(
            recommendation_pb2.UpdateUserProfileRequest(
                event=recommendation_pb2.InteractionEvent(
                    user_id=str(user_id),
                    book_id=book_id,
                    interaction_type=interaction_type,
                    value=float(value),
                )
            )
        )
        return bool(resp.success)
    except grpc.aio.AioRpcError as exc:
        logger.warning("Recommendation UpdateUserProfile failed: %s", exc)
        return False

