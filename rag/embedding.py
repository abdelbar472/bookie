"""Embedding generation for retrieval pipelines."""

import logging
from typing import List, Tuple

from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

try:
    import openai
except Exception:  # pragma: no cover
    openai = None

from rag.config import settings

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for text using OpenAI API."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if openai else None
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION

    def availability_status(self) -> Tuple[bool, str]:
        if self.client is None:
            return False, "openai package is not installed. Install dependencies from rag/requirements.txt"
        if not settings.OPENAI_API_KEY:
            return False, "OPENAI_API_KEY is not set for rag-service"
        return True, ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(RuntimeError),
        reraise=True,
    )
    async def generate(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        available, reason = self.availability_status()
        if not available:
            raise RuntimeError(reason)

        response = await self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    async def generate_single(self, text: str) -> List[float]:
        embeddings = await self.generate([text])
        return embeddings[0] if embeddings else []


embedding_generator = EmbeddingGenerator()

