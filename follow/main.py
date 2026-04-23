import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .config import settings
from .database import create_db_and_tables
from .routers import router
from .auth import close_auth_channel
from .grpc_server import serve_grpc

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Follow service startup – creating DB tables…")
    await create_db_and_tables()
    logger.info("✅ DB tables ready")

    logger.info(
        "🔌 Will connect to Auth gRPC at %s:%s",
        settings.AUTH_GRPC_HOST,
        settings.AUTH_GRPC_PORT,
    )

    grpc_server = await serve_grpc(host=settings.GRPC_HOST, port=settings.GRPC_PORT)
    logger.info(
        "🎯 Follow service ready  HTTP :8003  gRPC :%s",
        settings.GRPC_PORT,
    )

    yield

    logger.info("🛑 Stopping Follow gRPC server…")
    await grpc_server.stop(grace=5)
    logger.info("🛑 Closing Auth gRPC channel…")
    await close_auth_channel()
    logger.info("🛑 Follow service shutdown complete")


app = FastAPI(
    title="Follow Service",
    description=(
        "Manages follow relationships between users.\n\n"
        "- **HTTP** – REST endpoints for follow/unfollow/list (authenticated via gRPC → Auth).\n"
        "- **gRPC** – internal FollowService for other micro-services."
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
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "https://localhost:8080",  # Edge sometimes uses https for localhost
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")

