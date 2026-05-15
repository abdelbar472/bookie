from decouple import config
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "book_db_v3"

    # Collections
    BOOKS_COLLECTION: str = "books"
    AUTHORS_COLLECTION: str = "authors"
    SERIES_COLLECTION: str = "series"

    # App
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8007
    GRPC_PORT: int = 50057

    # Enrichment
    CACHE_TTL_DAYS: int = 30

    # External
    GOOGLE_BOOKS_API_KEY: Optional[str] = config("GOOGLE_BOOKS_API_KEY")

    # RAG Service
    RAG_SERVICE_GRPC_HOST: str = "localhost"
    RAG_SERVICE_GRPC_PORT: int = 50055

    # Social Service
    SOCIAL_SERVICE_GRPC_HOST: str = "localhost"
    SOCIAL_SERVICE_GRPC_PORT: int = 50054

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'


settings = Settings()