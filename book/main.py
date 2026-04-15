"""
Book Service V3 - Main Application Entry Point
FastAPI application with MongoDB integration
"""
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import connect_to_mongo, close_mongo_connection, db
from .grpc_server import grpc_server
from .routers import router
from .config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info("=" * 50)
    logger.info(f"Starting {settings.SERVICE_NAME} v3.0.0")
    logger.info("=" * 50)

    # Connect to MongoDB
    connected = await connect_to_mongo()
    if not connected:
        logger.warning("Running in EXTERNAL-ONLY mode (no caching)")

    await grpc_server.start()

    yield

    # Shutdown
    logger.info("Shutting down...")
    await grpc_server.stop()
    await close_mongo_connection()


# Create FastAPI app
app = FastAPI(
    title="Book Service V3",
    description="""
    Book catalog and enrichment service.

    Features:
    - Multi-source book aggregation (Google Books, OpenLibrary)
    - Author metadata enrichment for catalog quality
    - Series detection and reading order metadata
    - Cached book/author/series search APIs
    """,
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, tags=["v3"])


# Root endpoint
@app.get("/")
async def root():
    return {
        "service": settings.SERVICE_NAME,
        "version": "3.0.0",
        "status": "running",
        "docs": "/docs",
        "database": "connected" if db.is_connected else "disconnected",
        "ports": {
            "http": settings.HTTP_PORT,
            "grpc": settings.GRPC_PORT,
        },
    }


if __name__ == "__main__":
    uvicorn.run(
        "book.main:app",
        host="0.0.0.0",
        port=settings.HTTP_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )