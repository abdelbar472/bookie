"""Recommendation service entrypoint."""

import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .grpc_client import close_rag_channel
from .grpc_server import grpc_server
from .routers import router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await grpc_server.start()
    yield
    await close_rag_channel()
    await grpc_server.stop()


app = FastAPI(
    title="Recommendation Service",
    description="Standalone ranking and recommendation API backed by rag retrieval.",
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, tags=["recommendation"])


@app.get("/")
async def root():
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "status": "running",
        "rag_grpc": f"{settings.RAG_GRPC_HOST}:{settings.RAG_GRPC_PORT}",
        "grpc": f"{settings.GRPC_HOST}:{settings.GRPC_PORT}",
    }


if __name__ == "__main__":
    uvicorn.run(
        "recommendation.main:app",
        host="127.0.0.1",
        port=settings.HTTP_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
