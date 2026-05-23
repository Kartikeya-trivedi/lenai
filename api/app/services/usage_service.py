"""
Usage metering — records usage per request and provides aggregate dashboard data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UsageRecord
from app.schemas.usage import DailyUsage, UsageByModality, UsageSummary
from app.utils.logging import get_logger

logger = get_logger(__name__)


class UsageService:
    """Metering and usage analytics."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_usage(
        self,
        job_id: uuid.UUID,
        api_key_id: uuid.UUID,
        tenant_id: uuid.UUID,
        modality: str,
        compute_time_ms: int,
        input_size_bytes: int = 0,
        output_size_bytes: int = 0,
    ) -> UsageRecord:
        """Record a usage event for a completed job."""
        record = UsageRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            job_id=job_id,
            modality=modality,
            compute_time_ms=compute_time_ms,
            input_size_bytes=input_size_bytes,
            output_size_bytes=output_size_bytes,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_usage_summary(
        self,
        tenant_id: uuid.UUID,
        api_key_id: Optional[uuid.UUID] = None,
        days: int = 30,
    ) -> UsageSummary:
        """Get aggregate usage summary for a tenant."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = select(
            func.count(UsageRecord.id).label("total_requests"),
            func.coalesce(func.sum(UsageRecord.compute_time_ms), 0).label("total_compute_ms"),
            func.coalesce(func.sum(UsageRecord.output_size_bytes), 0).label("total_storage_bytes"),
        ).where(
            UsageRecord.tenant_id == tenant_id,
            UsageRecord.created_at >= since,
        )

        if api_key_id:
            stmt = stmt.where(UsageRecord.api_key_id == api_key_id)

        result = await self.db.execute(stmt)
        row = result.one()

        return UsageSummary(
            total_requests=row.total_requests,
            total_errors=0,  # TODO: join with jobs table for error count
            total_compute_ms=row.total_compute_ms,
            total_storage_bytes=row.total_storage_bytes,
            quota_remaining=0,  # Populated by caller with rate limiter data
        )

    async def get_usage_by_modality(
        self,
        tenant_id: uuid.UUID,
        days: int = 30,
    ) -> List[UsageByModality]:
        """Get usage breakdown per modality."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(
                UsageRecord.modality,
                func.count(UsageRecord.id).label("request_count"),
                func.coalesce(func.avg(UsageRecord.compute_time_ms), 0).label("avg_latency_ms"),
                func.coalesce(func.sum(UsageRecord.compute_time_ms), 0).label("total_compute_ms"),
            )
            .where(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.created_at >= since,
            )
            .group_by(UsageRecord.modality)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            UsageByModality(
                modality=row.modality,
                request_count=row.request_count,
                avg_latency_ms=round(float(row.avg_latency_ms), 2),
                error_count=0,
                total_compute_ms=row.total_compute_ms,
            )
            for row in rows
        ]

    async def get_daily_usage(
        self,
        tenant_id: uuid.UUID,
        days: int = 30,
    ) -> List[DailyUsage]:
        """Get daily usage time series."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(
                func.date(UsageRecord.created_at).label("day"),
                func.count(UsageRecord.id).label("request_count"),
                func.coalesce(func.avg(UsageRecord.compute_time_ms), 0).label("avg_latency_ms"),
            )
            .where(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.created_at >= since,
            )
            .group_by(func.date(UsageRecord.created_at))
            .order_by(func.date(UsageRecord.created_at))
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            DailyUsage(
                date=row.day,
                request_count=row.request_count,
                avg_latency_ms=round(float(row.avg_latency_ms), 2),
            )
            for row in rows
        ]
