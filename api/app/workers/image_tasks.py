"""
Image inference Celery task — Stable Diffusion txt2img and img2img.

Flow:
  1. Update job status → processing
  2. Call SD API (txt2img or img2img)
  3. Decode base64 result → upload to MinIO
  4. Generate presigned URL with TTL
  5. Update job → completed with output URL
  6. Dispatch webhook (if configured)
  7. Record usage metrics
"""

from __future__ import annotations

import base64
import io
import time
import traceback
import uuid

import httpx

from app.workers.celery_app import celery_app
from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _get_sync_session():
    """Create a synchronous DB session for Celery tasks.

    The engine is cached at module level to avoid creating a new connection
    pool on every task invocation (which would exhaust DB connections).
    """
    if not hasattr(_get_sync_session, "_engine"):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Convert async URL to sync
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace(
            "postgresql+asyncpg", "postgresql+psycopg2"
        )
        _get_sync_session._engine = create_engine(
            sync_url, pool_pre_ping=True, pool_size=5, max_overflow=5
        )
        _get_sync_session._SessionLocal = sessionmaker(bind=_get_sync_session._engine)

    return _get_sync_session._SessionLocal()


def _update_job_status(job_id: str, status: str, **kwargs):
    """Update job status and optional fields in the DB."""
    from datetime import datetime, timezone
    from app.models.job import Job

    session = _get_sync_session()
    try:
        job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if job:
            job.status = status
            for key, value in kwargs.items():
                setattr(job, key, value)
            if status == "processing" and not job.started_at:
                job.started_at = datetime.now(timezone.utc)
            if status in ("completed", "failed", "dead_letter"):
                job.completed_at = datetime.now(timezone.utc)
            session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("job_status_update_failed", job_id=job_id, error=str(exc))
    finally:
        session.close()


def _get_job(job_id: str):
    """Fetch a job record."""
    from app.models.job import Job

    session = _get_sync_session()
    try:
        job = session.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if job:
            # Detach from session for use after close
            session.expunge(job)
        return job
    finally:
        session.close()


def _record_usage(job_id: str, modality: str, compute_time_ms: int, output_size: int):
    """Record usage metrics for billing."""
    from app.models.usage import UsageRecord

    job = _get_job(job_id)
    if not job:
        return

    session = _get_sync_session()
    try:
        usage = UsageRecord(
            id=uuid.uuid4(),
            tenant_id=job.tenant_id,
            api_key_id=job.api_key_id,
            job_id=uuid.UUID(job_id),
            modality=modality,
            compute_time_ms=compute_time_ms,
            output_size_bytes=output_size,
        )
        session.add(usage)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("usage_record_failed", job_id=job_id, error=str(exc))
    finally:
        session.close()


@celery_app.task(
    name="workers.image_tasks.generate_image",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def generate_image(self, job_id: str):
    """
    Generate an image via Stable Diffusion API.

    Retry on transient failures (connection errors, 5xx from SD).
    Dead-letter on permanent failures (bad params, max retries exceeded).
    """
    logger.info("image_task_started", job_id=job_id, attempt=self.request.retries + 1)
    start_time = time.monotonic()

    # 1. Mark job as processing
    _update_job_status(job_id, "processing", progress=10)

    # 2. Fetch job params
    job = _get_job(job_id)
    if not job:
        logger.error("job_not_found", job_id=job_id)
        return

    params = job.input_params or {}

    try:
        _update_job_status(job_id, "processing", progress=20)

        import os
        if os.getenv("RUNNING_IN_MODAL") == "true":
            try:
                import sys
                if "/root" not in sys.path:
                    sys.path.append("/root")
                import modal_app
                f = modal_app.generate_image_modal
            except ImportError:
                import modal
                f = modal.Function.from_name("lenai-platform", "generate_image_modal")
            base64_img = f.remote(
                prompt=params.get("prompt", ""),
                negative_prompt=params.get("negative_prompt", ""),
                width=params.get("width", 512),
                height=params.get("height", 512),
                steps=params.get("steps", 20),
            )
            _update_job_status(job_id, "processing", progress=70)
            images = [base64_img]
        else:
            # 3. Call Stable Diffusion API locally
            sd_payload = {
                "prompt": params.get("prompt", ""),
                "negative_prompt": params.get("negative_prompt", ""),
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "steps": params.get("steps", 20),
                "cfg_scale": params.get("cfg_scale", 7.0),
                "seed": params.get("seed", -1),
                "batch_size": 1,
                "n_iter": 1,
            }

            with httpx.Client(timeout=300.0) as client:
                response = client.post(
                    f"{settings.SD_API_URL}/sdapi/v1/txt2img",
                    json=sd_payload,
                )

            _update_job_status(job_id, "processing", progress=70)

            if response.status_code != 200:
                raise RuntimeError(
                    f"SD API returned {response.status_code}: {response.text[:500]}"
                )

            result = response.json()
            images = result.get("images", [])
            if not images:
                raise RuntimeError("SD API returned no images")

        # 4. Decode base64 → upload to MinIO
        image_data = base64.b64decode(images[0])
        output_key = f"image/{job_id}/{uuid.uuid4()}.png"

        from app.services.storage import get_storage

        storage = get_storage()
        storage.upload_file(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=output_key,
            data=image_data,
            content_type="image/png",
        )

        _update_job_status(job_id, "processing", progress=85)

        # 5. Generate presigned URL
        output_url = storage.generate_presigned_url(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=output_key,
            ttl_hours=settings.OUTPUT_URL_TTL_HOURS,
        )

        # 6. Mark job completed
        compute_ms = int((time.monotonic() - start_time) * 1000)
        _update_job_status(
            job_id,
            "completed",
            progress=100,
            output_file_key=output_key,
            output_url=output_url,
        )

        logger.info(
            "image_task_completed",
            job_id=job_id,
            compute_time_ms=compute_ms,
            output_size=len(image_data),
        )

        # 7. Record usage
        _record_usage(job_id, "image", compute_ms, len(image_data))

        # 8. Dispatch webhook
        webhook_url = params.get("webhook_url") or job.webhook_url
        if webhook_url:
            from app.workers.webhook_tasks import deliver_webhook

            deliver_webhook.delay(
                job_id=job_id,
                webhook_url=webhook_url,
                event="job.completed",
            )

    except httpx.ConnectError as exc:
        logger.warning(
            "sd_connection_error",
            job_id=job_id,
            error=str(exc),
            retry=self.request.retries + 1,
        )
        _update_job_status(job_id, "queued", progress=0)
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

    except Exception as exc:
        error_trace = traceback.format_exc()
        logger.error(
            "image_task_failed",
            job_id=job_id,
            error=str(exc),
            traceback=error_trace,
        )

        if self.request.retries >= self.max_retries:
            # Dead-letter
            _update_job_status(
                job_id,
                "dead_letter",
                error_message=str(exc),
                error_trace=error_trace,
                retry_count=self.request.retries,
            )
            logger.error("image_task_dead_lettered", job_id=job_id)
        else:
            _update_job_status(
                job_id,
                "failed",
                error_message=str(exc),
                error_trace=error_trace,
                retry_count=self.request.retries,
            )
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
