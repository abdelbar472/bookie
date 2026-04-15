import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .config import settings
from .database import create_db_and_tables
from .routers import router
from .grpc_server import serve_grpc

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Auth service startup – creating DB tables…")
    await create_db_and_tables()
    logger.info("✅ DB tables ready")

    grpc_server = await serve_grpc(host="127.0.0.1", port=settings.GRPC_PORT)
    logger.info("Auth service ready  HTTP :%s  gRPC :%s", settings.HTTP_PORT, settings.GRPC_PORT)

    yield

    logger.info("🛑 Stopping gRPC server…")
    await grpc_server.stop(grace=5)
    logger.info("🛑 Auth service shutdown complete")


app = FastAPI(
    title="Auth Service",
    description="Handles login / signup / logout and issues JWTs. "
                "Exposes gRPC for internal token validation.",
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
