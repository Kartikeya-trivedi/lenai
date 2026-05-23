"""
E5 embedding service — encodes text into dense vectors for semantic search.

Uses the multilingual-e5-large model via the HuggingFace transformers library.
Falls back to sentence-transformers if available.

For production, this could be swapped to a vLLM embedding endpoint.
"""

from __future__ import annotations

import time
from typing import List, Optional

import numpy as np

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class EmbeddingService:
    """
    Dense text embedding using E5 models.

    E5 models expect a prefix:
      - "query: " for search queries
      - "passage: " for documents being indexed
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._model = None
        self._tokenizer = None
        self._dimension: Optional[int] = None

    def _load_model(self) -> None:
        """Lazy-load the embedding model."""
        if self._model is not None:
            return

        logger.info("loading_embedding_model", model=self.model_name)
        start = time.monotonic()

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            # Get dimension from a test embedding
            test = self._model.encode(["test"], normalize_embeddings=True)
            self._dimension = test.shape[1]
            self._use_st = True
        except ImportError:
            # Fallback to transformers directly
            import torch
            from transformers import AutoModel, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name)
            self._model.eval()
            self._use_st = False

            # Get dimension
            with torch.no_grad():
                inputs = self._tokenizer(
                    ["test"], return_tensors="pt", padding=True, truncation=True
                )
                outputs = self._model(**inputs)
                self._dimension = outputs.last_hidden_state.shape[-1]

        elapsed = round((time.monotonic() - start) * 1000)
        logger.info(
            "embedding_model_loaded",
            model=self.model_name,
            dimension=self._dimension,
            load_time_ms=elapsed,
        )

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed documents for indexing.
        Adds 'passage: ' prefix per E5 convention.
        """
        self._load_model()
        prefixed = [f"passage: {t}" for t in texts]
        return self._encode(prefixed)

    def embed_query(self, query: str) -> List[float]:
        """
        Embed a search query.
        Adds 'query: ' prefix per E5 convention.
        """
        self._load_model()
        prefixed = f"query: {query}"
        result = self._encode([prefixed])
        return result[0]

    def _encode(self, texts: List[str]) -> List[List[float]]:
        """Encode texts to normalized embedding vectors."""
        if self._use_st:
            embeddings = self._model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=32,
            )
            return embeddings.tolist()
        else:
            import torch

            with torch.no_grad():
                inputs = self._tokenizer(
                    texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512,
                )
                outputs = self._model(**inputs)
                # Mean pooling
                attention_mask = inputs["attention_mask"]
                token_embeddings = outputs.last_hidden_state
                input_mask_expanded = (
                    attention_mask.unsqueeze(-1)
                    .expand(token_embeddings.size())
                    .float()
                )
                embeddings = torch.sum(
                    token_embeddings * input_mask_expanded, 1
                ) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

                # L2 normalize
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                return embeddings.cpu().numpy().tolist()


# Module singleton
_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
