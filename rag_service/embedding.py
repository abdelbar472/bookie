"""Embedding generation for retrieval pipelines."""

import logging
from typing import List

from tenacity import retry, stop_after_attempt, wait_exponential

try:
    import openai
except Exception:  # pragma: no cover
    openai = None

from rag_service.config import settings

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for text using OpenAI API."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if openai else None
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.client is None:
            raise RuntimeError("openai package is not installed. Install dependencies from rag_service/requirements.txt")

        response = await self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    async def generate_single(self, text: str) -> List[float]:
        embeddings = await self.generate([text])
        return embeddings[0] if embeddings else []


embedding_generator = EmbeddingGenerator()

