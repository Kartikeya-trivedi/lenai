"""
Cross-encoder reranker — rescores retrieval candidates using a
cross-encoder model for more precise relevance estimation.

The cross-encoder sees (query, document) pairs jointly, unlike
the bi-encoder embeddings which encode them independently.
This gives much better relevance scores at the cost of speed
(only feasible on the top-K candidates, not the full corpus).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class Reranker:
    """
    Cross-encoder reranker using ms-marco-MiniLM.

    Rescores (query, passage) pairs and returns top-K by relevance.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or settings.RERANKER_MODEL
        self._model = None

    def _load_model(self) -> None:
        """Lazy-load the cross-encoder model."""
        if self._model is not None:
            return

        logger.info("loading_reranker", model=self.model_name)
        start = time.monotonic()

        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, max_length=512)
            self._use_ce = True
        except ImportError:
            # Fallback: use transformers directly
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            import torch

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name
            )
            self._model.eval()
            self._use_ce = False

        elapsed = round((time.monotonic() - start) * 1000)
        logger.info("reranker_loaded", model=self.model_name, load_time_ms=elapsed)

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
        text_key: str = "text",
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents by cross-encoder score.

        Args:
            query: The search query
            documents: List of document dicts (must contain `text_key` field)
            top_k: How many to return
            text_key: Which field in the document contains the text

        Returns:
            Documents sorted by reranker score (highest first),
            each with a 'rerank_score' field added.
        """
        self._load_model()

        if not documents:
            return []

        pairs = [(query, doc.get(text_key, "")) for doc in documents]

        start = time.monotonic()

        if self._use_ce:
            scores = self._model.predict(pairs, show_progress_bar=False)
        else:
            import torch

            with torch.no_grad():
                inputs = self._tokenizer(
                    pairs,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512,
                )
                outputs = self._model(**inputs)
                scores = outputs.logits.squeeze(-1).cpu().numpy()

        elapsed = round((time.monotonic() - start) * 1000)

        # Attach scores and sort
        scored_docs = []
        for doc, score in zip(documents, scores):
            scored_doc = {**doc, "rerank_score": round(float(score), 4)}
            scored_docs.append(scored_doc)

        scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)

        logger.info(
            "reranker_completed",
            query_length=len(query),
            input_docs=len(documents),
            output_docs=min(top_k, len(scored_docs)),
            latency_ms=elapsed,
        )

        return scored_docs[:top_k]


# Module singleton
_reranker: Optional[Reranker] = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker
