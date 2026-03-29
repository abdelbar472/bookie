from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "bookie"

    GOOGLE_BOOKS_API_KEY: str | None = None

    # gRPC - Recommendation service
    RECOMMENDATION_GRPC_HOST: str = "localhost"
    RECOMMENDATION_GRPC_PORT: int = 50058

    # gRPC - Social service (for notifications)
    SOCIAL_GRPC_HOST: str = "localhost"
    SOCIAL_GRPC_PORT: int = 50055

    HTTP_PORT: int = 8004


settings = Settings()