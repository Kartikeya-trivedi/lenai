"""
Job management endpoints — status polling, listing, DLQ queries.
"""

from __future__ import annotations

import math
import uuid
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_api_key
from app.models.api_key import ApiKey
from app.schemas.jobs import JobFilters, JobListResponse, JobResponse
from app.services.job_service import JobService
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/jobs", tags=["Jobs"])


def _job_response_with_output_data(job) -> JobResponse:
    response = JobResponse.model_validate(job)

    if (
        response.modality != "voice_stt"
        or response.status != "completed"
        or not getattr(job, "output_file_key", None)
    ):
        return response

    try:
        from app.config import get_settings
        from app.services.storage import get_storage

        settings = get_settings()
        transcript_bytes = get_storage().download_file(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=job.output_file_key,
        )
        response.output_data = json.loads(transcript_bytes.decode("utf-8"))
    except Exception as exc:
        logger.warning(
            "job_output_data_hydration_failed",
            job_id=str(job.id),
            error=str(exc),
        )

    return response


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status",
)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Get the current status of an inference job."""
    import os
    if os.getenv("SKIP_AUTH", "").lower() == "true":
        from app.demo_state import FAKE_JOBS
        from datetime import datetime, timezone
        if str(job_id) in FAKE_JOBS:
            data = FAKE_JOBS[str(job_id)]
            return JobResponse(
                id=job_id,
                status=data["status"],
                modality=data["modality"],
                output_url=data.get("output_url"),
                output_data=data.get("output_data"),
                error_message=data.get("error_message"),
                progress=data.get("progress", 0),
                created_at=datetime.now(timezone.utc),
                tenant_id=uuid.uuid4()
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found in demo state (server might have restarted)",
            )

    service = JobService(db)
    job = await service.get_job(job_id, api_key.tenant_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return _job_response_with_output_data(job)


@router.get(
    "",
    response_model=JobListResponse,
    summary="List jobs",
)
async def list_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status_filter: str = Query(default=None, alias="status"),
    modality: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """List jobs with pagination and optional filters."""
    filters = JobFilters(status=status_filter, modality=modality)
    service = JobService(db)
    jobs, total = await service.list_jobs(
        tenant_id=api_key.tenant_id,
        filters=filters,
        page=page,
        per_page=per_page,
    )

    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0,
    )


@router.get(
    "/dead-letter",
    response_model=JobListResponse,
    summary="List dead-letter jobs",
)
async def list_dead_letter_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """List all permanently failed jobs in the dead-letter queue."""
    service = JobService(db)
    jobs, total = await service.get_dead_letter_jobs(
        tenant_id=api_key.tenant_id,
        page=page,
        per_page=per_page,
    )

    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0,
    )
