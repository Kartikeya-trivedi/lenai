"""
RAG pipeline orchestrator — ties together retrieval, reranking,
confidence gating, and dual-tier LLM inference.

MediQuery Architecture:
  Query → Redis Cache Check
       → Hybrid Retrieval (BM25 + Qdrant)
       → Cross-Encoder Reranking
       → NLI Confidence Gate
       → LLM Generation (Small → Big model fallback)
       → Cache Result → Return
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.services.rag.reranker import get_reranker
from app.services.rag.retriever import get_hybrid_retriever
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class RAGPipeline:
    """
    Full clinical RAG pipeline with confidence-gated dual-tier inference.

    Flow:
      1. Check Redis cache for identical query
      2. Hybrid retrieval (dense + sparse + RRF)
      3. Cross-encoder reranking (top-K)
      4. NLI confidence gate on best passage
      5. If confidence HIGH  → Small LLM (Llama 3.1 8B) + context
         If confidence LOW   → Big LLM (Gemma 27B) + extended context
         If confidence NONE  → Return "no relevant info found"
      6. Cache response in Redis
    """

    def __init__(self) -> None:
        self.retriever = get_hybrid_retriever()
        self.reranker = get_reranker()
        self._redis = None

    async def _get_redis(self):
        """Lazy Redis connection for caching."""
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        return self._redis

    async def query(
        self,
        question: str,
        top_k: int = 10,
        rerank_top_k: int = 5,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute the full RAG pipeline.

        Returns:
            {
                "answer": str,
                "confidence": float,
                "model_used": str,
                "sources": [...],
                "retrieval_stats": {...},
                "cached": bool,
            }
        """
        start = time.monotonic()
        cache_key = f"rag:cache:{hashlib.md5(question.encode()).hexdigest()}"

        # ── 1. Cache check ─────────────────────────────────────
        if use_cache:
            try:
                r = await self._get_redis()
                cached = await r.get(cache_key)
                if cached:
                    result = json.loads(cached)
                    result["cached"] = True
                    logger.info("rag_cache_hit", query=question[:50])
                    return result
            except Exception:
                pass  # Redis down → proceed without cache

        # ── 2. Hybrid retrieval ────────────────────────────────
        retrieval_start = time.monotonic()
        candidates = await self.retriever.retrieve(
            query=question,
            top_k=top_k,
        )
        retrieval_ms = round((time.monotonic() - retrieval_start) * 1000)

        if not candidates:
            return {
                "answer": "No relevant information found in the knowledge base.",
                "confidence": 0.0,
                "model_used": "none",
                "sources": [],
                "retrieval_stats": {"candidates": 0, "retrieval_ms": retrieval_ms},
                "cached": False,
            }

        # ── 3. Cross-encoder reranking ─────────────────────────
        rerank_start = time.monotonic()
        reranked = self.reranker.rerank(
            query=question,
            documents=candidates,
            top_k=rerank_top_k,
        )
        rerank_ms = round((time.monotonic() - rerank_start) * 1000)

        # ── 4. NLI confidence gate ─────────────────────────────
        best_score = reranked[0].get("rerank_score", 0.0) if reranked else 0.0
        confidence = self._compute_confidence(best_score, reranked)

        # ── 5. LLM generation ─────────────────────────────────
        context = self._build_context(reranked)
        sources = [
            {
                "text": doc.get("text", "")[:200],
                "source": doc.get("source", ""),
                "score": doc.get("rerank_score", 0.0),
            }
            for doc in reranked
        ]

        if confidence < settings.RAG_CONFIDENCE_THRESHOLD:
            # Below threshold — no confident answer possible
            answer = (
                "I found some potentially related information, but I'm not confident "
                "enough to provide a reliable answer. Please consult a medical "
                "professional for this query."
            )
            model_used = "none (below confidence threshold)"
        elif confidence < 0.7:
            # Medium confidence → use big model for better reasoning
            answer = await self._generate(
                question, context, model="big", max_tokens=1024
            )
            model_used = settings.LLM_MODEL_LARGE
        else:
            # High confidence → small model is sufficient
            answer = await self._generate(
                question, context, model="small", max_tokens=512
            )
            model_used = settings.LLM_MODEL

        total_ms = round((time.monotonic() - start) * 1000)

        result = {
            "answer": answer,
            "confidence": round(confidence, 4),
            "model_used": model_used,
            "sources": sources,
            "retrieval_stats": {
                "candidates": len(candidates),
                "reranked": len(reranked),
                "retrieval_ms": retrieval_ms,
                "rerank_ms": rerank_ms,
                "total_ms": total_ms,
            },
            "cached": False,
        }

        # ── 6. Cache result ────────────────────────────────────
        if use_cache and confidence >= settings.RAG_CONFIDENCE_THRESHOLD:
            try:
                r = await self._get_redis()
                await r.setex(
                    cache_key,
                    3600,  # 1 hour TTL
                    json.dumps(result),
                )
            except Exception:
                pass

        logger.info(
            "rag_pipeline_completed",
            query=question[:50],
            confidence=round(confidence, 4),
            model_used=model_used,
            total_ms=total_ms,
        )

        return result

    def _compute_confidence(
        self,
        best_score: float,
        reranked: List[Dict[str, Any]],
    ) -> float:
        """
        Compute confidence score from reranker outputs.

        Uses the best reranker score normalized to [0, 1] range.
        Cross-encoder scores are typically in [-10, 10] range.
        """
        if not reranked:
            return 0.0

        # Sigmoid normalization of the cross-encoder score
        import math
        normalized = 1.0 / (1.0 + math.exp(-best_score))

        # Boost if multiple high-scoring passages agree
        if len(reranked) >= 3:
            top3_avg = sum(
                d.get("rerank_score", 0.0) for d in reranked[:3]
            ) / 3
            agreement_bonus = max(0, 1.0 / (1.0 + math.exp(-top3_avg)) - 0.5) * 0.2
            normalized = min(1.0, normalized + agreement_bonus)

        return normalized

    def _build_context(self, documents: List[Dict[str, Any]]) -> str:
        """Build context string from retrieved documents."""
        parts = []
        for i, doc in enumerate(documents, 1):
            source = doc.get("source", "unknown")
            text = doc.get("text", "")
            parts.append(f"[Source {i}: {source}]\n{text}")
        return "\n\n---\n\n".join(parts)

    async def _generate(
        self,
        question: str,
        context: str,
        model: str = "small",
        max_tokens: int = 512,
    ) -> str:
        """
        Generate answer using vLLM-compatible API.

        Routes to small (Llama 3.1 8B) or big (Gemma 27B) model.
        """
        if model == "big":
            model_name = settings.LLM_MODEL_LARGE
        else:
            model_name = settings.LLM_MODEL

        system_prompt = (
            "You are a clinical assistant. Answer the question using ONLY the "
            "provided context. If the context doesn't contain enough information "
            "to answer, say so. Be precise and cite your sources. "
            "Do not fabricate information."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Context:\n{context}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer based only on the context above:"
                ),
            },
        ]

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{settings.VLLM_API_URL}/v1/chat/completions",
                    json={
                        "model": model_name,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": 0.1,
                        "top_p": 0.95,
                    },
                )
                resp.raise_for_status()

            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            return answer.strip()

        except Exception as e:
            logger.error(
                "llm_generation_failed",
                model=model_name,
                error=str(e),
            )
            return (
                f"I was unable to generate a response due to a model error: {str(e)}. "
                f"Please try again later."
            )
