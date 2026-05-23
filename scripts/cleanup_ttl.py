"""
TTL cleanup script — deletes expired output files from MinIO.

Runs as a periodic task (via Celery beat or cron).
Removes output files whose presigned URLs have expired.

Usage:
  python -m scripts.cleanup_ttl
  # or via Makefile:
  make clean
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_factory
from app.models.job import Job
from app.services.storage import get_storage
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def cleanup_expired_outputs():
    """
    Find jobs with expired output URLs and delete the associated MinIO objects.
    This prevents storage from growing unbounded.
    """
    storage = get_storage()
    deleted_count = 0
    error_count = 0

    async with async_session_factory() as session:
        # Find completed jobs with expired output URLs
        result = await session.execute(
            select(Job).where(
                Job.status == "completed",
                Job.output_file_key.isnot(None),
                Job.output_url_expires_at.isnot(None),
                Job.output_url_expires_at < datetime.now(timezone.utc),
            )
        )
        expired_jobs = result.scalars().all()

        logger.info("cleanup_started", expired_jobs_count=len(expired_jobs))

        for job in expired_jobs:
            try:
                # Delete from MinIO
                storage.delete_file(
                    bucket=settings.MINIO_BUCKET_OUTPUTS,
                    key=job.output_file_key,
                )
                # Clear URLs on the job
                job.output_url = None
                job.output_file_key = None
                job.output_url_expires_at = None
                deleted_count += 1

            except Exception as exc:
                logger.warning(
                    "cleanup_file_failed",
                    job_id=str(job.id),
                    key=job.output_file_key,
                    error=str(exc),
                )
                error_count += 1

        await session.commit()

    logger.info(
        "cleanup_completed",
        deleted=deleted_count,
        errors=error_count,
    )
    print(f"✅ Cleanup complete: {deleted_count} files deleted, {error_count} errors")


if __name__ == "__main__":
    asyncio.run(cleanup_expired_outputs())
