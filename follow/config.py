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

    DATABASE_URL: str = "sqlite+aiosqlite:///./follow_service.db"
    LOG_LEVEL: str = "INFO"

    # gRPC – Auth service (for token validation)
    AUTH_GRPC_HOST: str = "localhost"
    AUTH_GRPC_PORT: int = 50051

    # gRPC – this service exposes a gRPC server
    GRPC_HOST: str = "0.0.0.0"       # bind address
    GRPC_PORT: int = 50052

    # gRPC – address other services use to reach THIS service
    FOLLOW_GRPC_HOST: str = "localhost"


settings = Settings()

