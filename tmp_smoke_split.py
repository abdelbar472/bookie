import asyncio

from rag_service.grpc_server import grpc_server as rag_grpc
from recommendation.grpc_server import grpc_server as rec_grpc
from recommendation.service import RecommendationService
from social.recommendation_grpc_client import (
    close_recommendation_channel as close_social_channel,
    track_interaction,
)
from recommendation.grpc_client import close_rag_channel


async def main() -> None:
    await rag_grpc.start()
    await rec_grpc.start()
    try:
        initial = await RecommendationService.get_recommendations(
            user_id="u1",
            history_book_ids=["book-123"],
            top_k=5,
            diversify=True,
        )
        print("rec_direct_ok", initial.get("source"), initial.get("count"))

        ok = await track_interaction(
            user_id=1,
            book_id="book-123",
            interaction_type="like",
            value=1.0,
        )
        print("social_event_ok", ok)

        profiled = await RecommendationService.get_recommendations(
            user_id="1",
            history_book_ids=[],
            top_k=5,
            diversify=True,
        )
        print("profile_recommend_ok", len(profiled.get("based_on", [])), profiled.get("count"))
    finally:
        await close_social_channel()
        await close_rag_channel()
        await rec_grpc.stop()
        await rag_grpc.stop()


if __name__ == "__main__":
    asyncio.run(main())

