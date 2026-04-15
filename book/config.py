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

    # External Service URLs
    RAG_SERVICE_URL: str | None = None
    SOCIAL_SERVICE_URL: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()