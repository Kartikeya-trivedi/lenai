"""
TTL Cleanup — periodic task that removes expired output files from MinIO
and updates job records. Prevents storage from growing unbounded.

Runs on Celery Beat schedule (configurable via CLEANUP_INTERVAL_MINUTES).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from app.workers.celery_app import celery_app

# Avoid importing full app config at module level (Celery worker boot)
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://lenai:changeme@postgres:5432/lenai"
)
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_USE_SSL = os.environ.get("MINIO_USE_SSL", "false").lower() == "true"
MINIO_BUCKET_OUTPUTS = os.environ.get("MINIO_BUCKET_OUTPUTS", "outputs")


def _get_sync_engine():
    """Cached sync engine for cleanup tasks."""
    if not hasattr(_get_sync_engine, "_engine"):
        from sqlalchemy import create_engine

        sync_url = DATABASE_URL.replace("+asyncpg", "").replace(
            "postgresql+asyncpg", "postgresql+psycopg2"
        )
        _get_sync_engine._engine = create_engine(
            sync_url, pool_pre_ping=True, pool_size=2, max_overflow=2
        )
    return _get_sync_engine._engine


def _get_minio_client():
    """Cached MinIO client for cleanup tasks."""
    if not hasattr(_get_minio_client, "_client"):
        from minio import Minio

        _get_minio_client._client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ROOT_USER,
            secret_key=MINIO_ROOT_PASSWORD,
            secure=MINIO_USE_SSL,
        )
    return _get_minio_client._client


@celery_app.task(
    name="workers.cleanup_tasks.cleanup_expired_outputs",
    bind=True,
    max_retries=1,
    soft_time_limit=120,
    time_limit=180,
)
def cleanup_expired_outputs(self):
    """
    Scan for jobs with expired output URLs, delete the MinIO objects,
    and clear the output fields in the database.

    This ensures storage doesn't grow unbounded. Expired outputs
    are no longer accessible via presigned URL anyway.
    """
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    engine = _get_sync_engine()
    Session = sessionmaker(bind=engine)
    session = Session()

    now = datetime.now(timezone.utc)
    deleted_count = 0
    error_count = 0

    try:
        # Find jobs with expired output URLs
        result = session.execute(
            text("""
                SELECT id, output_file_key
                FROM jobs
                WHERE output_url_expires_at IS NOT NULL
                  AND output_url_expires_at < :now
                  AND output_file_key IS NOT NULL
                ORDER BY output_url_expires_at ASC
                LIMIT 100
            """),
            {"now": now},
        )
        expired_jobs = result.fetchall()

        if not expired_jobs:
            return {"cleaned": 0, "errors": 0, "message": "No expired outputs found"}

        minio = _get_minio_client()

        for job_id, output_file_key in expired_jobs:
            try:
                # Delete from MinIO
                minio.remove_object(MINIO_BUCKET_OUTPUTS, output_file_key)

                # Clear output fields in DB
                session.execute(
                    text("""
                        UPDATE jobs
                        SET output_file_key = NULL,
                            output_url = NULL,
                            output_url_expires_at = NULL
                        WHERE id = :job_id
                    """),
                    {"job_id": job_id},
                )
                deleted_count += 1

            except Exception as e:
                # Object might already be gone — that's fine
                error_count += 1
                # Still clear the DB fields so we don't retry forever
                session.execute(
                    text("""
                        UPDATE jobs
                        SET output_url = NULL,
                            output_url_expires_at = NULL
                        WHERE id = :job_id
                    """),
                    {"job_id": job_id},
                )

        session.commit()

    except Exception as exc:
        session.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        session.close()

    return {
        "cleaned": deleted_count,
        "errors": error_count,
        "scanned_at": now.isoformat(),
    }
