"""Core retrieval engine: indexing and vector search orchestration."""

import logging
from typing import Any, Dict, List, Optional

from .embedding import embedding_generator
from .vector_store import vector_store

logger = logging.getLogger(__name__)


class RAGEngine:
    def __init__(self):
        self.embedding_gen = embedding_generator
        self.vector_store = vector_store
        self._embedding_unavailable_logged = False

    def _embedding_is_ready(self) -> bool:
        available, reason = self.embedding_gen.availability_status()
        if not available and not self._embedding_unavailable_logged:
            logger.warning("RAG embedding unavailable. Skipping indexing until fixed: %s", reason)
            self._embedding_unavailable_logged = True
        return available

    async def index_book(self, book: Dict[str, Any]) -> bool:
        try:
            documents: List[Dict[str, Any]] = []
            if book.get("rag_document"):
                documents.append(
                    {
                        "id": f"book:{book['work_id']}",
                        "text": book["rag_document"],
                        "work_id": book["work_id"],
                        "entity_type": "book",
                        "title": book.get("title", ""),
                        "author": book.get("primary_author", ""),
                        "genres": book.get("genres", []),
                        "themes": book.get("content_analysis", {}).get("key_themes", []),
                    }
                )
            if book.get("description"):
                documents.append(
                    {
                        "id": f"desc:{book['work_id']}",
                        "text": f"{book.get('title', '')} by {book.get('primary_author', '')}. {book['description']}",
                        "work_id": book["work_id"],
                        "entity_type": "description",
                        "title": book.get("title", ""),
                        "author": book.get("primary_author", ""),
                        "genres": book.get("genres", []),
                        "themes": [],
                    }
                )
            if not documents:
                return False
            if not self._embedding_is_ready():
                return False
            embeddings = await self.embedding_gen.generate([doc["text"] for doc in documents])
            return await self.vector_store.upsert_documents(documents, embeddings)
        except Exception as exc:
            logger.error("Failed to index book %s: %s", book.get("title"), exc)
            return False

    async def index_author(self, author: Dict[str, Any]) -> bool:
        try:
            if not author.get("rag_document"):
                return False
            if not self._embedding_is_ready():
                return False
            document = {
                "id": f"author:{author['author_id']}",
                "text": author["rag_document"],
                "author_id": author["author_id"],
                "entity_type": "author",
                "title": author.get("name", ""),
                "author": author.get("name", ""),
                "genres": author.get("style_profile", {}).get("genres", []),
                "themes": author.get("style_profile", {}).get("common_themes", []),
            }
            embedding = await self.embedding_gen.generate_single(document["text"])
            return await self.vector_store.upsert_documents([document], [embedding])
        except Exception:
            return False

    async def search(self, query: str, top_k: int = 5, entity_type: Optional[str] = None, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        query_embedding = await self.embedding_gen.generate_single(query)
        search_filters = dict(filters or {})
        if entity_type:
            search_filters["entity_type"] = entity_type
        return await self.vector_store.hybrid_search(
            query_embedding=query_embedding,
            query_text=query,
            top_k=top_k,
            filters=search_filters if search_filters else None,
        )

    async def recommend_similar(self, work_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        book_doc = await self.vector_store.get_by_id(f"book:{work_id}")
        if not book_doc:
            return []
        query_embedding = await self.embedding_gen.generate_single(book_doc["text"])
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k + 1,
            filters={"entity_type": "book"},
        )
        return [item for item in results if item.get("work_id") != work_id][:top_k]


rag_engine = RAGEngine()

