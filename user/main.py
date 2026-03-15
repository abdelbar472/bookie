import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .config import settings
from .database import create_db_and_tables
from .routers import router
from .grpc_client import close_grpc_channel
from .follow_grpc_client import close_follow_channel

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 User service startup – creating DB tables…")
    await create_db_and_tables()
    logger.info("✅ DB tables ready")
    logger.info(
        "🔌 Will connect to Auth gRPC at %s:%s",
        settings.AUTH_GRPC_HOST,
        settings.AUTH_GRPC_PORT,
    )
    logger.info(
        "🔌 Will connect to Follow gRPC at %s:%s",
        settings.FOLLOW_GRPC_HOST,
        settings.FOLLOW_GRPC_PORT,
    )
    yield
    logger.info("🛑 Closing Auth gRPC channel…")
    await close_grpc_channel()
    logger.info("🛑 Closing Follow gRPC channel…")
    await close_follow_channel()
    logger.info("🛑 User service shutdown complete")


app = FastAPI(
    title="User Service",
    description="Manages user profiles. Delegates all auth (JWT) to the Auth service via gRPC.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    print(f">> {request.method} {request.url.path} from {request.client.host if request.client else '?'}", flush=True)
    response = await call_next(request)
    elapsed = time.time() - t0
    print(f"<< {request.method} {request.url.path} - {response.status_code} ({elapsed:.3f}s)", flush=True)
    return response


app.include_router(router, prefix="/api/v1")

