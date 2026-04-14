"""RAG Service package."""

__version__ = "1.0.0"

from .rag_engine import rag_engine
from .services import RecommendationService, SearchService

__all__ = ["rag_engine", "SearchService", "RecommendationService"]

