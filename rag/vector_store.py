"""Vector store operations for retrieval."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from rag.config import settings
from .qdrant_client import get_qdrant

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self):
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.qdrant = None

    def _get_client(self):
        if self.qdrant is None:
            self.qdrant = get_qdrant()
        return self.qdrant

    async def upsert_documents(self, documents: List[Dict[str, Any]], embeddings: List[List[float]]) -> bool:
        try:
            client = self._get_client()
            points: List[PointStruct] = []
            for doc, embedding in zip(documents, embeddings):
                points.append(
                    PointStruct(
                        id=doc["id"],
                        vector=embedding,
                        payload={
                            "text": doc["text"],
                            "work_id": doc.get("work_id"),
                            "author_id": doc.get("author_id"),
                            "series_id": doc.get("series_id"),
                            "entity_type": doc.get("entity_type", "book"),
                            "title": doc.get("title"),
                            "author": doc.get("author"),
                            "genres": doc.get("genres", []),
                            "themes": doc.get("themes", []),
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )
                )
            client.upsert(collection_name=self.collection_name, points=points)
            logger.info("Upserted %s documents", len(points))
            return True
        except Exception as exc:
            logger.error("Failed to upsert documents: %s", exc)
            return False

    async def search(self, query_embedding: List[float], top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            qdrant_filter = self._build_filter(filters) if filters else None
            results = client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
                with_vectors=False,
            )
            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "text": r.payload.get("text"),
                    "work_id": r.payload.get("work_id"),
                    "author_id": r.payload.get("author_id"),
                    "series_id": r.payload.get("series_id"),
                    "entity_type": r.payload.get("entity_type"),
                    "title": r.payload.get("title"),
                    "author": r.payload.get("author"),
                    "genres": r.payload.get("genres", []),
                    "themes": r.payload.get("themes", []),
                }
                for r in results
            ]
        except Exception as exc:
            logger.error("Search failed: %s", exc)
            return []

    async def hybrid_search(self, query_embedding: List[float], query_text: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        results = await self.search(query_embedding, top_k * 2, filters)
        terms = query_text.lower().split()
        for result in results:
            text = (result.get("text") or "").lower()
            matches = sum(1 for term in terms if term in text)
            result["score"] = result["score"] * (1 + min(0.2, matches * 0.05))
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]

    async def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        try:
            client = self._get_client()
            result = client.retrieve(collection_name=self.collection_name, ids=[doc_id], with_payload=True)
            if not result:
                return None
            first = result[0]
            return {"id": first.id, "text": first.payload.get("text"), "work_id": first.payload.get("work_id"), "metadata": first.payload}
        except Exception as exc:
            logger.error("Retrieve failed: %s", exc)
            return None

    async def count(self) -> int:
        try:
            client = self._get_client()
            info = client.get_collection(self.collection_name)
            return int(info.points_count or 0)
        except Exception:
            return 0

    def _build_filter(self, filters: Dict[str, Any]) -> Optional[Filter]:
        conditions = []
        if "entity_type" in filters:
            conditions.append(FieldCondition(key="entity_type", match=MatchValue(value=filters["entity_type"])))
        if "work_id" in filters:
            conditions.append(FieldCondition(key="work_id", match=MatchValue(value=filters["work_id"])))
        return Filter(must=conditions) if conditions else None


vector_store = VectorStore()

