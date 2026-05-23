"""
Health check endpoints — liveness and readiness probes.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.common import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def liveness():
    """Liveness probe — is the API process running?"""
    return HealthResponse(status="ok", version="1.0.0")


@router.get("/readiness", response_model=HealthResponse)
async def readiness():
    """
    Readiness probe — are all dependencies healthy?
    Checks: database, Redis, MinIO, model containers.
    """
    service = HealthService()
    services = await service.check_all()
    overall = await service.get_overall_status()

    return HealthResponse(
        status=overall,
        version="1.0.0",
        services=services,
    )
