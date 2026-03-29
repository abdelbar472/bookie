import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .database import get_database, close_database
from .routers import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Book V2 starting...")
    await get_database()
    yield
    await close_database()

app = FastAPI(title="Book Service V2", version="2.0.0", lifespan=lifespan)
app.include_router(router, prefix="/api/v2")
