"""
RAG / MediQuery endpoints — clinical knowledge base query and ingestion.

Endpoints:
  POST /v1/rag/query     — Query the knowledge base
  POST /v1/rag/ingest    — Ingest a document
  POST /v1/rag/ingest/batch — Ingest multiple documents
  GET  /v1/rag/stats     — Knowledge base statistics
  DELETE /v1/rag/document — Delete a document by source
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_api_key
from app.models.api_key import ApiKey
from app.schemas.rag import (
    IngestBatchRequest,
    IngestBatchResponse,
    IngestDocumentRequest,
    IngestResponse,
    KnowledgeBaseStats,
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1/rag", tags=["RAG / MediQuery"])


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="Query the clinical knowledge base",
    description=(
        "Runs the full RAG pipeline: hybrid retrieval (BM25 + Qdrant), "
        "cross-encoder reranking, confidence gating, and dual-tier LLM generation."
    ),
)
async def query_knowledge_base(
    request: RAGQueryRequest,
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Execute a RAG query against the clinical knowledge base."""
    import os
    if os.getenv("SKIP_AUTH", "").lower() == "true":
        # Direct vLLM chat bypassing Qdrant (for demo)
        import httpx
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                res = await client.post(
                    f"{settings.VLLM_API_URL}/v1/chat/completions",
                    json={
                        "model": "meta-llama/Llama-3.1-8B-Instruct",
                        "messages": [{"role": "user", "content": request.question}],
                        "max_tokens": 1024,
                    }
                )
                res.raise_for_status()
                answer = res.json()["choices"][0]["message"]["content"]
            return RAGQueryResponse(
                question=request.question,
                answer=answer,
                sources=[],
                confidence=1.0,
                model_used="meta-llama/Llama-3.1-8B-Instruct (Direct Mode)",
                retrieval_stats={"candidates": 0, "reranked": 0, "retrieval_ms": 0, "rerank_ms": 0, "total_ms": 0},
                cached=False
            )
        except Exception as e:
            return RAGQueryResponse(
                question=request.question,
                answer=f"Error connecting to vLLM: {str(e)}",
                sources=[],
                confidence=0.0,
                model_used="error",
                retrieval_stats={"candidates": 0, "reranked": 0, "retrieval_ms": 0, "rerank_ms": 0, "total_ms": 0},
                cached=False
            )

    from app.services.rag.pipeline import RAGPipeline

    pipeline = RAGPipeline()

    result = await pipeline.query(
        question=request.question,
        top_k=request.top_k,
        rerank_top_k=request.rerank_top_k,
        use_cache=request.use_cache,
    )

    return RAGQueryResponse(**result)


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest a document into the knowledge base",
    description="Chunks the document, embeds with E5, and stores in Qdrant.",
)
async def ingest_document(
    request: IngestDocumentRequest,
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Ingest a single document."""
    from app.services.rag.ingestion import IngestionService

    service = IngestionService()
    result = await service.ingest_document(
        text=request.text,
        source=request.source,
        metadata=request.metadata,
    )

    return IngestResponse(**result)


@router.post(
    "/ingest/batch",
    response_model=IngestBatchResponse,
    summary="Batch ingest documents",
)
async def ingest_batch(
    request: IngestBatchRequest,
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Ingest multiple documents."""
    from app.services.rag.ingestion import IngestionService

    service = IngestionService()
    results = await service.ingest_batch(
        documents=[doc.model_dump() for doc in request.documents]
    )

    total_chunks = sum(r.get("chunks", 0) for r in results)

    return IngestBatchResponse(
        results=[IngestResponse(**r) for r in results],
        total_documents=len(results),
        total_chunks=total_chunks,
    )


@router.get(
    "/stats",
    response_model=KnowledgeBaseStats,
    summary="Knowledge base statistics",
)
async def get_kb_stats(
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Get statistics about the knowledge base."""
    from app.services.rag.qdrant_store import get_qdrant_client

    qdrant = get_qdrant_client()
    total_chunks = await qdrant.count()

    return KnowledgeBaseStats(
        total_documents=0,  # Would need a metadata query to count unique sources
        total_chunks=total_chunks,
        embedding_model=settings.EMBEDDING_MODEL,
        reranker_model=settings.RERANKER_MODEL,
        llm_model_small=settings.LLM_MODEL,
        llm_model_large=settings.LLM_MODEL_LARGE,
    )


@router.delete(
    "/document",
    summary="Delete a document by source",
)
async def delete_document(
    source: str,
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Delete all chunks for a document from the knowledge base."""
    from app.services.rag.ingestion import IngestionService

    service = IngestionService()
    await service.delete_document(source)

    return {"status": "deleted", "source": source}
