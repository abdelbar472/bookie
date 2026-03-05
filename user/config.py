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

    # gRPC address of the Auth service
    AUTH_GRPC_HOST: str = "localhost"
    AUTH_GRPC_PORT: int = 50051


settings = Settings()

