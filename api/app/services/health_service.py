"""
Health aggregation — checks every dependency and reports status.
"""

from __future__ import annotations

from typing import Any, Dict

from app.database import check_db_health
from app.middleware.rate_limiter import check_redis_health
from app.services.model_registry import get_model_registry
from app.services.storage import get_storage
from app.utils.logging import get_logger

logger = get_logger(__name__)


class HealthService:
    """Aggregates health status of all dependencies."""

    async def check_all(self) -> Dict[str, Dict[str, Any]]:
        """Check health of all services. Returns per-service status."""
        results = {}

        # Database
        healthy, latency = await check_db_health()
        results["database"] = {
            "status": "ok" if healthy else "unhealthy",
            "latency_ms": latency,
        }

        # Redis
        healthy, latency = await check_redis_health()
        results["redis"] = {
            "status": "ok" if healthy else "unhealthy",
            "latency_ms": latency,
        }

        # MinIO
        storage = get_storage()
        healthy, latency = storage.check_health()
        results["minio"] = {
            "status": "ok" if healthy else "unhealthy",
            "latency_ms": latency,
        }

        # Models
        registry = get_model_registry()
        for model in registry.get_all_models():
            healthy, latency = await registry.check_model_health(model.modality)
            results[f"model_{model.name}"] = {
                "status": "ok" if healthy else "unhealthy",
                "modality": model.modality,
                "latency_ms": latency,
            }

        # Qdrant vector store
        try:
            from app.services.rag.qdrant_store import get_qdrant_client

            qdrant = get_qdrant_client()
            healthy, latency = await qdrant.health_check()
            results["qdrant"] = {
                "status": "ok" if healthy else "unhealthy",
                "latency_ms": latency,
            }
        except Exception:
            results["qdrant"] = {"status": "unavailable", "latency_ms": 0}

        return results

    async def get_overall_status(self) -> str:
        """Get overall system status: ok, degraded, or unhealthy."""
        services = await self.check_all()

        critical = ["database", "redis", "minio"]
        critical_healthy = all(
            services.get(s, {}).get("status") == "ok" for s in critical
        )

        if not critical_healthy:
            return "unhealthy"

        all_healthy = all(s["status"] == "ok" for s in services.values())
        return "ok" if all_healthy else "degraded"
