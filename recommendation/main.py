import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .config import settings
from .vector_store import init_qdrant
from .grpc_server import serve_grpc
from .routers import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Recommendation Service starting...")
    await init_qdrant()
    grpc_server = await serve_grpc()
    yield
    await grpc_server.stop(grace=5)

app = FastAPI(title="Recommendation Service", version="1.0.0", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")