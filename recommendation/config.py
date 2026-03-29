from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    HTTP_PORT: int = 8008
    GRPC_PORT: int = 50058

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "bookie_recommendations"

    # Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    VECTOR_DIM: int = 384

    # Scoring weights
    WEIGHT_CONTENT: float = 0.4
    WEIGHT_AUTHOR_STYLE: float = 0.3
    WEIGHT_USER_BEHAVIOR: float = 0.2
    WEIGHT_SOCIAL: float = 0.1

    # Social service (for real-time signals)
    SOCIAL_GRPC_HOST: str = "localhost"
    SOCIAL_GRPC_PORT: int = 50055


settings = Settings()