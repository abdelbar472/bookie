import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .auth import close_auth_channel
from .book_grpc_client import close_book_channel
from .config import settings
from .db import close_database, get_database
from .grpc_server import serve_grpc
from .routers import router
from .v3 import close_client, get_client, setup_database

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RAG service startup - preparing vector DB and Mongo indexes")

    qdrant_client = await asyncio.to_thread(get_client)
    await asyncio.to_thread(setup_database, qdrant_client)
    mongo_db = await get_database()

    rag_grpc_server = await serve_grpc(
        db=mongo_db,
        qdrant_client=qdrant_client,
        host=settings.GRPC_HOST,
        port=settings.GRPC_PORT,
    )

    logger.info("RAG service ready")
    yield

    logger.info("RAG service shutdown - closing resources")
    await rag_grpc_server.stop(grace=5)
    await asyncio.to_thread(lambda: close_client(qdrant_client))
    await close_auth_channel()
    await close_book_channel()
    await close_database()


app = FastAPI(
    title="RAG Service",
    description=(
        "RAG recommendations, user reading lists, and personalized vectors.\n\n"
        "- Uses Qdrant for semantic retrieval\n"
        "- Uses MongoDB for reading history and taste profiles\n"
        "- Pulls canonical book metadata from Book service via gRPC"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    print(
        f">> {request.method} {request.url.path} "
        f"from {request.client.host if request.client else '?'}",
        flush=True,
    )
    response = await call_next(request)
    elapsed = time.time() - t0
    print(
        f"<< {request.method} {request.url.path} "
        f"- {response.status_code} ({elapsed:.3f}s)",
        flush=True,
    )
    return response


app.include_router(router)

