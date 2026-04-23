import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .auth import close_auth_channel
from .book_grpc_client import close_book_channel
from .config import settings
from .database import create_db_and_tables
from .recommendation_grpc_client import close_recommendation_channel
from .grpc_server import serve_grpc
from .routers import router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Social service startup - creating DB tables")
    await create_db_and_tables()
    logger.info("Social DB tables ready")
    grpc_server = await serve_grpc(host=settings.GRPC_HOST, port=settings.GRPC_PORT)
    logger.info("Social service ready  HTTP :%s  gRPC :%s", settings.HTTP_PORT, settings.GRPC_PORT)
    yield
    logger.info("Social service shutdown - stopping gRPC and closing channels")
    await grpc_server.stop(grace=5)
    await close_auth_channel()
    await close_book_channel()
    await close_recommendation_channel()


app = FastAPI(
    title="Social Service",
    description=(
        "Book social interactions: likes, ratings, reviews, and shelves.\n\n"
        "Requires Bearer auth via Auth gRPC and validates ISBN via Book gRPC."
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
