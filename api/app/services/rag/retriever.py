"""
Hybrid retriever — combines dense (Qdrant) and sparse (BM25) retrieval
with Reciprocal Rank Fusion (RRF) for merging ranked lists.

Architecture:
  Query → [Dense Search (Qdrant)] + [Sparse Search (BM25)]
       → RRF Fusion → Top-K candidates → Reranker → Final results
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import get_settings
from app.services.rag.embeddings import get_embedding_service
from app.services.rag.qdrant_store import get_qdrant_client
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ── BM25 Sparse Retriever ─────────────────────────────────────
class BM25Index:
    """
    In-memory BM25 index for sparse retrieval.

    Built from documents stored in Qdrant (loaded on first query).
    For production scale, replace with Elasticsearch or Qdrant's
    built-in sparse vectors.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_freqs: Dict[str, int] = {}
        self.doc_lengths: List[int] = []
        self.avg_dl: float = 0.0
        self.doc_count: int = 0
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        self.documents: List[Dict[str, Any]] = []
        self._built = False

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Simple whitespace + lowercase tokenizer with stopword removal."""
        tokens = re.findall(r"\b\w+\b", text.lower())
        # Minimal stopwords
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "of", "in", "to", "for", "with", "on", "at", "by", "from",
            "and", "or", "but", "not", "no", "this", "that", "it",
        }
        return [t for t in tokens if t not in stopwords and len(t) > 1]

    def build(self, documents: List[Dict[str, Any]]) -> None:
        """Build the BM25 index from a list of documents."""
        self.documents = documents
        self.doc_count = len(documents)

        for doc_idx, doc in enumerate(documents):
            tokens = self.tokenize(doc.get("text", ""))
            self.doc_lengths.append(len(tokens))

            term_freq = Counter(tokens)
            for term, freq in term_freq.items():
                self.inverted_index[term].append((doc_idx, freq))

            for term in set(tokens):
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        self.avg_dl = sum(self.doc_lengths) / max(self.doc_count, 1)
        self._built = True

        logger.info(
            "bm25_index_built",
            doc_count=self.doc_count,
            vocab_size=len(self.doc_freqs),
        )

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Score all documents against query, return top-K."""
        if not self._built or self.doc_count == 0:
            return []

        query_tokens = self.tokenize(query)
        scores: Dict[int, float] = defaultdict(float)

        for token in query_tokens:
            if token not in self.inverted_index:
                continue

            df = self.doc_freqs.get(token, 0)
            idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1.0)

            for doc_idx, tf in self.inverted_index[token]:
                dl = self.doc_lengths[doc_idx]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * dl / self.avg_dl
                )
                scores[doc_idx] += idf * numerator / denominator

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        return [
            {
                **self.documents[doc_idx],
                "bm25_score": round(score, 4),
            }
            for doc_idx, score in ranked
        ]


# ── Reciprocal Rank Fusion ────────────────────────────────────
def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    k: int = 60,
    id_key: str = "id",
) -> List[Dict[str, Any]]:
    """
    Merge multiple ranked result lists using RRF.
    Score = Σ 1 / (k + rank_i) for each list containing the document.
    """
    scores: Dict[str, float] = defaultdict(float)
    docs: Dict[str, Dict[str, Any]] = {}

    for ranked_list in ranked_lists:
        for rank, doc in enumerate(ranked_list, start=1):
            doc_id = doc.get(id_key, str(rank))
            scores[doc_id] += 1.0 / (k + rank)
            if doc_id not in docs:
                docs[doc_id] = doc

    # Sort by fused score
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {**docs[doc_id], "rrf_score": round(score, 6)}
        for doc_id, score in fused
        if doc_id in docs
    ]


# ── Hybrid Retriever ──────────────────────────────────────────
class HybridRetriever:
    """
    Combines dense (Qdrant semantic) and sparse (BM25) retrieval
    with RRF fusion for robust recall.
    """

    def __init__(self) -> None:
        self.embedder = get_embedding_service()
        self.qdrant = get_qdrant_client()
        self.bm25 = BM25Index()
        self._bm25_loaded = False

    async def _ensure_bm25(self) -> None:
        """Build BM25 index from Qdrant if not already loaded."""
        if self._bm25_loaded:
            return

        # Fetch all documents from Qdrant for BM25 indexing
        # In production, this would use a streaming scroll or
        # an Elasticsearch sidecar instead
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.qdrant.base_url}/collections/clinical_docs/points/scroll",
                json={"limit": 10000, "with_payload": True},
            )
            if resp.status_code != 200:
                logger.warning("bm25_scroll_failed", status=resp.status_code)
                self._bm25_loaded = True
                return

            points = resp.json().get("result", {}).get("points", [])

        if points:
            docs = [
                {
                    "id": str(p["id"]),
                    "text": p["payload"].get("text", ""),
                    "source": p["payload"].get("source", ""),
                    "metadata": p["payload"].get("metadata", {}),
                }
                for p in points
            ]
            self.bm25.build(docs)

        self._bm25_loaded = True

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval:
          1. Dense search via Qdrant (E5 embeddings)
          2. Sparse search via BM25
          3. Merge with RRF
        """
        # Dense retrieval
        query_vector = self.embedder.embed_query(query)
        dense_results = await self.qdrant.search(
            query_vector=query_vector,
            top_k=top_k * 2,  # Fetch more for fusion
        )

        # Sparse retrieval
        await self._ensure_bm25()
        sparse_results = self.bm25.search(query, top_k=top_k * 2)

        # Assign IDs to BM25 results for fusion if missing
        for i, doc in enumerate(sparse_results):
            if "id" not in doc:
                doc["id"] = f"bm25_{i}"

        # Fuse with RRF
        fused = reciprocal_rank_fusion(
            [dense_results, sparse_results],
            id_key="id",
        )

        logger.info(
            "hybrid_retrieval",
            query_length=len(query),
            dense_hits=len(dense_results),
            sparse_hits=len(sparse_results),
            fused_total=len(fused),
        )

        return fused[:top_k]


# Module singleton
_retriever: Optional[HybridRetriever] = None


def get_hybrid_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
