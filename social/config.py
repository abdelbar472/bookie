from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_ignore_empty=True,
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite+aiosqlite:///./social_service.db"
    LOG_LEVEL: str = "INFO"

    AUTH_GRPC_HOST: str = "localhost"
    AUTH_GRPC_PORT: int = 50051

    BOOK_GRPC_HOST: str = "localhost"
    BOOK_GRPC_PORT: int = 50054


settings = Settings()

