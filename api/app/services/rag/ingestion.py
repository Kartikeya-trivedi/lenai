"""
Document chunking and ingestion pipeline.

Splits documents into overlapping chunks, embeds them, and stores
in Qdrant for hybrid retrieval.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.services.rag.embeddings import get_embedding_service
from app.services.rag.qdrant_store import get_qdrant_client
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> List[str]:
    """
    Split text into overlapping chunks by token count (approximate via words).

    Uses word boundaries to avoid cutting mid-word.
    """
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - chunk_overlap

    return chunks


class IngestionService:
    """Ingests documents into the RAG pipeline."""

    def __init__(self) -> None:
        self.embedder = get_embedding_service()
        self.qdrant = get_qdrant_client()
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP

    async def ingest_document(
        self,
        text: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest a single document:
          1. Chunk the text
          2. Embed all chunks
          3. Upsert into Qdrant with metadata

        Returns ingestion stats.
        """
        metadata = metadata or {}

        # Ensure collection exists
        await self.qdrant.ensure_collection(vector_size=self.embedder.dimension)

        # Chunk
        chunks = chunk_text(text, self.chunk_size, self.chunk_overlap)
        if not chunks:
            return {"status": "empty", "chunks": 0}

        logger.info("ingestion_chunked", source=source, chunks=len(chunks))

        # Embed
        vectors = self.embedder.embed_documents(chunks)

        # Build point IDs and payloads
        source_hash = hashlib.md5(source.encode()).hexdigest()[:8]
        point_ids = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}::{i}"))
            for i in range(len(chunks))
        ]
        payloads = [
            {
                "text": chunk,
                "source": source,
                "chunk_index": i,
                "metadata": metadata,
                "source_hash": source_hash,
            }
            for i, chunk in enumerate(chunks)
        ]

        # Upsert
        # Qdrant expects UUID strings
        await self.qdrant.upsert_points(
            ids=point_ids,
            vectors=vectors,
            payloads=payloads,
        )

        logger.info(
            "ingestion_complete",
            source=source,
            chunks=len(chunks),
            vector_dim=len(vectors[0]),
        )

        return {
            "status": "ingested",
            "source": source,
            "chunks": len(chunks),
            "vector_dimension": len(vectors[0]),
        }

    async def ingest_batch(
        self,
        documents: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """
        Ingest multiple documents.
        Each dict must have 'text' and 'source' keys.
        """
        results = []
        for doc in documents:
            result = await self.ingest_document(
                text=doc["text"],
                source=doc["source"],
                metadata=doc.get("metadata", {}),
            )
            results.append(result)
        return results

    async def delete_document(self, source: str) -> None:
        """Remove all chunks for a document by source identifier."""
        await self.qdrant.delete_by_source(source)
        logger.info("document_deleted", source=source)
