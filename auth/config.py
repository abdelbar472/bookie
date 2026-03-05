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

    DATABASE_URL: str = "sqlite+aiosqlite:///./auth_service.db"
    SECRET_KEY: str = "change_me_in_production"
    ALGORITHM: str = "HS256"

    LOG_LEVEL: str = "INFO"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # gRPC – this service exposes a gRPC server
    GRPC_PORT: int = 50051


settings = Settings()

