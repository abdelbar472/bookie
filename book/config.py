"""
Configuration management for Book Service V3
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # API Keys
    GOOGLE_BOOKS_API_KEY: str | None = Field(default=None, alias="GOOGLE_API_KEY")

    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "book_db_v3"

    # Service
    SERVICE_NAME: str = "book-service-v3"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    HTTP_PORT: int = 8007
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50057

    # Enrichment
    MAX_BOOKS_PER_QUERY: int = 20
    ENABLE_ARABIC_SEARCH: bool = True
    AUTHOR_SEARCH_MIN_RESULTS: int = 5

    # External API reliability
    EXTERNAL_TIMEOUT_SECONDS: float = 10.0
    EXTERNAL_RETRY_ATTEMPTS: int = 3
    ENABLE_OPENLIBRARY_AUTHOR_WORKS: bool = True
    ENABLE_WIKIDATA_ALIASES: bool = True
    WIKIDATA_MAX_ALIASES: int = 20

    # External Service URLs
    RAG_SERVICE_URL: str | None = None
    SOCIAL_SERVICE_URL: str | None = None

    # RAG Service gRPC (optional indexing notification)
    RAG_SERVICE_GRPC_HOST: str = "localhost"
    RAG_SERVICE_GRPC_PORT: int = 50055
    ENABLE_RAG_NOTIFICATION: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()