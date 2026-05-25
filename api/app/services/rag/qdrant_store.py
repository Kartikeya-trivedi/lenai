"""
Qdrant vector store client for the RAG pipeline.

Manages document embeddings, upsert, and semantic search.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

COLLECTION_NAME = "clinical_docs"


class QdrantClient:
    """HTTP client for Qdrant vector database."""

    def __init__(self, url: Optional[str] = None) -> None:
        self.base_url = (url or settings.QDRANT_URL).rstrip("/")
        self.headers = {}
        if settings.QDRANT_API_KEY:
            self.headers["api-key"] = settings.QDRANT_API_KEY

    async def ensure_collection(self, vector_size: int = 1024) -> None:
        """Create collection if it doesn't exist."""
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            # Check if collection exists
            resp = await client.get(
                f"{self.base_url}/collections/{COLLECTION_NAME}"
            )
            if resp.status_code == 200:
                logger.info("qdrant_collection_exists", name=COLLECTION_NAME)
                return

            # Create collection
            resp = await client.put(
                f"{self.base_url}/collections/{COLLECTION_NAME}",
                json={
                    "vectors": {
                        "size": vector_size,
                        "distance": "Cosine",
                    },
                    "optimizers_config": {
                        "indexing_threshold": 10000,
                    },
                },
            )
            resp.raise_for_status()
            logger.info(
                "qdrant_collection_created",
                name=COLLECTION_NAME,
                vector_size=vector_size,
            )

    async def upsert_points(
        self,
        ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
    ) -> None:
        """Upsert document chunks with their embeddings."""
        points = []
        for point_id, vector, payload in zip(ids, vectors, payloads):
            points.append({
                "id": point_id,
                "vector": vector,
                "payload": payload,
            })

        async with httpx.AsyncClient(timeout=60.0, headers=self.headers) as client:
            resp = await client.put(
                f"{self.base_url}/collections/{COLLECTION_NAME}/points",
                json={"points": points},
            )
            resp.raise_for_status()

        logger.info("qdrant_upserted", count=len(points))

    async def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filter_conditions: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search — returns scored results with payloads."""
        body: Dict[str, Any] = {
            "vector": query_vector,
            "limit": top_k,
            "with_payload": True,
            "score_threshold": score_threshold,
        }
        if filter_conditions:
            body["filter"] = filter_conditions

        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            resp = await client.post(
                f"{self.base_url}/collections/{COLLECTION_NAME}/points/search",
                json=body,
            )
            resp.raise_for_status()

        results = resp.json().get("result", [])
        return [
            {
                "id": r["id"],
                "score": r["score"],
                "text": r["payload"].get("text", ""),
                "metadata": r["payload"].get("metadata", {}),
                "source": r["payload"].get("source", ""),
                "chunk_index": r["payload"].get("chunk_index", 0),
            }
            for r in results
        ]

    async def delete_by_source(self, source: str) -> None:
        """Delete all points from a specific source document."""
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            resp = await client.post(
                f"{self.base_url}/collections/{COLLECTION_NAME}/points/delete",
                json={
                    "filter": {
                        "must": [
                            {"key": "source", "match": {"value": source}}
                        ]
                    }
                },
            )
            resp.raise_for_status()

        logger.info("qdrant_deleted_by_source", source=source)

    async def count(self) -> int:
        """Get total point count in collection."""
        async with httpx.AsyncClient(timeout=10.0, headers=self.headers) as client:
            resp = await client.get(
                f"{self.base_url}/collections/{COLLECTION_NAME}"
            )
            resp.raise_for_status()

        return resp.json().get("result", {}).get("points_count", 0)

    async def health_check(self) -> tuple[bool, float]:
        """Check Qdrant connectivity."""
        import time

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5.0, headers=self.headers) as client:
                resp = await client.get(f"{self.base_url}/healthz")
                latency = (time.monotonic() - start) * 1000
                return resp.status_code == 200, round(latency, 2)
        except Exception:
            latency = (time.monotonic() - start) * 1000
            return False, round(latency, 2)


# Module singleton
_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient()
    return _client
