"""
Pydantic schemas for the RAG / MediQuery endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Query ──────────────────────────────────────────────────
class RAGQueryRequest(BaseModel):
    """Query the clinical knowledge base."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural language question",
    )
    top_k: int = Field(
        default=10, ge=1, le=50,
        description="Number of retrieval candidates",
    )
    rerank_top_k: int = Field(
        default=5, ge=1, le=20,
        description="Number of candidates to keep after reranking",
    )
    use_cache: bool = Field(
        default=True,
        description="Whether to check/store in Redis cache",
    )


class RAGSource(BaseModel):
    """A retrieved source passage."""

    text: str
    source: str
    score: float


class RAGRetrievalStats(BaseModel):
    """Performance metrics for the retrieval pipeline."""

    candidates: int
    reranked: int = 0
    retrieval_ms: int = 0
    rerank_ms: int = 0
    total_ms: int = 0


class RAGQueryResponse(BaseModel):
    """Full RAG query response."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    model_used: str
    sources: List[RAGSource]
    retrieval_stats: RAGRetrievalStats
    cached: bool = False


# ── Ingestion ──────────────────────────────────────────────
class IngestDocumentRequest(BaseModel):
    """Ingest a single document into the knowledge base."""

    text: str = Field(
        ..., min_length=10,
        description="Document text content",
    )
    source: str = Field(
        ..., min_length=1,
        description="Source identifier (e.g., filename, DOI, URL)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata (category, author, date, etc.)",
    )


class IngestBatchRequest(BaseModel):
    """Ingest multiple documents."""

    documents: List[IngestDocumentRequest] = Field(
        ..., min_length=1, max_length=100,
    )


class IngestResponse(BaseModel):
    """Result of document ingestion."""

    status: str
    source: str = ""
    chunks: int = 0
    vector_dimension: int = 0


class IngestBatchResponse(BaseModel):
    """Result of batch ingestion."""

    results: List[IngestResponse]
    total_documents: int
    total_chunks: int


# ── Knowledge Base ─────────────────────────────────────────
class KnowledgeBaseStats(BaseModel):
    """Statistics about the knowledge base."""

    total_documents: int = 0
    total_chunks: int = 0
    embedding_model: str = ""
    reranker_model: str = ""
    llm_model_small: str = ""
    llm_model_large: str = ""
