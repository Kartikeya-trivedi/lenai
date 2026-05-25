"""
Application configuration via Pydantic BaseSettings.
All values loaded from environment / .env file — nothing hardcoded.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── PostgreSQL ──────────────────────────────────────────────
    POSTGRES_USER: str = "lenai"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_DB: str = "lenai"
    DATABASE_URL: str = "postgresql+asyncpg://lenai:changeme@postgres:5432/lenai"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def enforce_asyncpg(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # ── Redis ───────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── MinIO Object Storage ────────────────────────────────────
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin"
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_PUBLIC_ENDPOINT: str = "localhost:9000"
    MINIO_USE_SSL: bool = False
    MINIO_BUCKET_INPUTS: str = "inputs"
    MINIO_BUCKET_OUTPUTS: str = "outputs"

    # ── API Server ──────────────────────────────────────────────
    API_SECRET_KEY: str = "changeme_api_secret_key_min_32_characters"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 1
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    CORS_ORIGINS: str = '["http://localhost","http://localhost:80","http://localhost:3000"]'

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list) -> str:
        if isinstance(v, list):
            return json.dumps(v)
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    # ── Self-Hosted Model Endpoints ─────────────────────────────
    SD_API_URL: str = "http://sd:7860"
    WHISPER_API_URL: str = "http://whisper:9000"
    KOKORO_API_URL: str = "http://kokoro:8880"
    VLLM_API_URL: str = "http://vllm:8000"

    # ── RAG Pipeline ────────────────────────────────────────────
    QDRANT_URL: str = "http://qdrant:6333"
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    LLM_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"
    LLM_MODEL_LARGE: str = "google/gemma-2-27b-it"
    RAG_CONFIDENCE_THRESHOLD: float = 0.3
    RAG_TOP_K: int = 10
    RAG_RERANK_TOP_K: int = 5
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50

    # ── Storage & Cleanup ───────────────────────────────────────
    OUTPUT_URL_TTL_HOURS: int = 24
    MAX_UPLOAD_SIZE_MB: int = 100
    CLEANUP_INTERVAL_MINUTES: int = 60

    # ── Webhook ─────────────────────────────────────────────────
    WEBHOOK_MAX_RETRIES: int = 5
    WEBHOOK_TIMEOUT_SECONDS: int = 30

    # ── Rate Limiting ───────────────────────────────────────────
    DEFAULT_RATE_LIMIT_RPM: int = 60
    DEFAULT_MONTHLY_CAP: int = 10000

    # ── Modal (optional) ────────────────────────────────────────
    MODAL_TOKEN_ID: Optional[str] = None
    MODAL_TOKEN_SECRET: Optional[str] = None
    MODAL_ENVIRONMENT: str = "dev"

    # ── GPU ──────────────────────────────────────────────────────
    USE_GPU: bool = False
    CUDA_VISIBLE_DEVICES: str = "0"

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — parsed once per process."""
    return Settings()
