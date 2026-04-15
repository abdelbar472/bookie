from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_ignore_empty=True,
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite+aiosqlite:///./user_service.db"
    LOG_LEVEL: str = "INFO"

    HTTP_PORT: int = 8002

    # gRPC server exposed by this service
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50052

    # gRPC address of the Auth service
    AUTH_GRPC_HOST: str = "localhost"
    AUTH_GRPC_PORT: int = 50051

    # gRPC address of the Follow service
    FOLLOW_GRPC_HOST: str = "localhost"
    FOLLOW_GRPC_PORT: int = 50053


settings = Settings()
