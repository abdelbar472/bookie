
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Service
    SERVICE_NAME: str = "rag-service"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API Keys
    OPENAI_API_KEY: str | None = None

    # Vector Database (Qdrant)
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "book_embeddings"

    # Embeddings
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    # gRPC
    GRPC_PORT: int = 50056
    GRPC_HOST: str = "0.0.0.0"

    # Book Service V3 gRPC
    BOOK_V3_GRPC_HOST: str = "localhost"
    BOOK_V3_GRPC_PORT: int = 50057


    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


