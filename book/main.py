"""
Book Service V4 - Fixed Imports
"""

import logging
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from contextlib import asynccontextmanager

from config import settings
from database import db
from grpc_server import start_grpc_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    grpc_server = await start_grpc_server(host=settings.HOST, port=settings.GRPC_PORT)
    logger.info(f"🚀 Book Service V4 started on port {settings.PORT}")
    yield
    await grpc_server.stop(0)
    await db.close()
    logger.info("👋 Book Service shutdown")


app = FastAPI(
    title="Bookie Core V4",
    description="On-demand Book Enrichment Service",
    version="4.0.0",
    lifespan=lifespan
)

# Import router
from routers.api import router as api_router
app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "service": "Bookie Core V4",
        "status": "running",
        "port": settings.PORT,
        "database": settings.MONGODB_DB_NAME
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
