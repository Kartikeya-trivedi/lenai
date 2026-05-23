"""
Usage dashboard endpoint — GET /v1/usage
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_api_key
from app.models.api_key import ApiKey
from app.schemas.usage import UsageDashboardResponse
from app.services.usage_service import UsageService

router = APIRouter(prefix="/v1", tags=["Usage"])


@router.get(
    "/usage",
    response_model=UsageDashboardResponse,
    summary="Get usage dashboard",
    description="Returns aggregate usage statistics for the authenticated tenant.",
)
async def get_usage_dashboard(
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    modality: Optional[str] = Query(default=None, description="Filter by modality"),
):
    """
    Usage dashboard with aggregate stats, per-modality breakdown, and daily time series.
    """
    service = UsageService(db)

    summary = await service.get_usage_summary(
        tenant_id=api_key.tenant_id,
        days=days,
    )
    by_modality = await service.get_usage_by_modality(
        tenant_id=api_key.tenant_id,
        days=days,
    )
    daily = await service.get_daily_usage(
        tenant_id=api_key.tenant_id,
        days=days,
    )

    return UsageDashboardResponse(
        summary=summary,
        by_modality=by_modality,
        daily=daily,
    )
