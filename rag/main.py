"""RAG Service main entry point.
Starts HTTP API and gRPC server.
"""
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .grpc_client import book_service_client
from .grpc_server import grpc_server
from rag.qdrant_client import DatabaseManager
from .routers import router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("Starting %s v%s", settings.SERVICE_NAME, settings.VERSION)
    logger.info("=" * 50)

    await DatabaseManager.connect()
    await book_service_client.connect()
    await grpc_server.start()

    yield

    logger.info("Shutting down...")
    await grpc_server.stop()
    await book_service_client.close()
    await DatabaseManager.close()


app = FastAPI(
    title="RAG Service",
    description=(
        "Retrieval and indexing service for books/authors.\n\n"
        "HTTP (8005): retrieval/indexing APIs\n"
        "gRPC (50055): internal communication"
    ),
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, tags=["rag"])


@app.get("/")
async def root():
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "status": "running",
        "ports": {"http": settings.HTTP_PORT, "grpc": settings.GRPC_PORT},
        "docs": "/docs",
    }


@app.get("/health")
async def health_compat():
    from rag import vector_store

    try:
        count = await vector_store.count()
        return {"status": "healthy", "indexed_documents": count, "version": settings.VERSION}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc), "version": settings.VERSION}


if __name__ == "__main__":
    uvicorn.run(
        "rag.main:app",
        host="0.0.0.0",
        port=settings.HTTP_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
