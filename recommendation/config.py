from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SERVICE_NAME: str = "recommendation-service"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # RAG retrieval gRPC server
    RAG_GRPC_HOST: str = "localhost"
    RAG_GRPC_PORT: int = 50056

    # gRPC server (consumed by rag_service)
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50058

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

