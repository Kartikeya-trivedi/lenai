"""
Job CRUD service — status queries, updates, DLQ access.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.schemas.jobs import JobFilters
from app.utils.logging import get_logger

logger = get_logger(__name__)


class JobService:
    """Database operations for jobs."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_job(
        self,
        job_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Optional[Job]:
        """Get a single job by ID, scoped to tenant."""
        stmt = select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        tenant_id: uuid.UUID,
        filters: JobFilters,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Job], int]:
        """List jobs with filters and pagination."""
        stmt = select(Job).where(Job.tenant_id == tenant_id)

        if filters.status:
            stmt = stmt.where(Job.status == filters.status)
        if filters.modality:
            stmt = stmt.where(Job.modality == filters.modality)
        if filters.date_from:
            stmt = stmt.where(Job.created_at >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(Job.created_at <= filters.date_to)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Paginate
        stmt = stmt.order_by(Job.created_at.desc())
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(stmt)
        jobs = list(result.scalars().all())

        return jobs, total

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: str,
        **kwargs,
    ) -> Optional[Job]:
        """Update a job's status and optional fields."""
        stmt = select(Job).where(Job.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return None

        job.status = status
        job.updated_at = datetime.now(timezone.utc)

        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        if status == JobStatus.PROCESSING.value:
            job.started_at = datetime.now(timezone.utc)
        elif status in (JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value):
            job.completed_at = datetime.now(timezone.utc)

        await self.db.flush()

        logger.info(
            "job_status_updated",
            job_id=str(job_id),
            new_status=status,
        )

        return job

    async def get_dead_letter_jobs(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Job], int]:
        """List all dead-lettered jobs for a tenant."""
        stmt = select(Job).where(
            Job.tenant_id == tenant_id,
            Job.status == JobStatus.DEAD_LETTER.value,
        )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(Job.created_at.desc())
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(stmt)
        jobs = list(result.scalars().all())

        return jobs, total

    async def increment_retry(self, job_id: uuid.UUID) -> Optional[Job]:
        """Increment retry count and check if job should be dead-lettered."""
        stmt = select(Job).where(Job.id == job_id)
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return None

        job.retry_count += 1
        if job.retry_count >= job.max_retries:
            job.status = JobStatus.DEAD_LETTER.value
            job.completed_at = datetime.now(timezone.utc)
            logger.warning(
                "job_dead_lettered",
                job_id=str(job_id),
                retry_count=job.retry_count,
            )
        else:
            job.status = JobStatus.QUEUED.value

        await self.db.flush()
        return job
