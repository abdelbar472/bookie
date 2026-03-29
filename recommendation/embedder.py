import logging
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer

from .config import settings

logger = logging.getLogger(__name__)
_model = None


def get_model():
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def generate_book_embeddings(book: dict) -> dict:
    """Generate multiple embeddings for a book"""
    model = get_model()

    # Content embedding (title + description + categories)
    content_parts = [book["title"]]
    if book.get("description"):
        content_parts.append(book["description"][:500])
    content_parts.extend(book.get("categories", []))
    content_text = " | ".join(content_parts)

    # Author style embedding (authors + writing style hints)
    author_text = f"Authors: {', '.join(book.get('authors', []))}"
    if book.get("categories"):
        author_text += f". Genres: {', '.join(book['categories'])}"

    return {
        "content": model.encode(content_text).tolist(),
        "author_style": model.encode(author_text).tolist(),
    }


def generate_query_embedding(query: str) -> List[float]:
    """Embed user query"""
    return get_model().encode(query).tolist()