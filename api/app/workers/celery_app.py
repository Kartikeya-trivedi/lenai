"""
Celery application configuration.

Broker: Redis with persistence (AOF).
Task routes: modality-specific queues for resource isolation.
Retry policy: exponential backoff, 3 retries, then dead-letter.
"""

from __future__ import annotations

import os

from celery import Celery

# Use env var or default — avoids importing app.config (which needs pydantic-settings at worker boot)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "lenai_workers",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    # ── Serialization ──────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,  # 1 hour

    # ── Task routing ───────────────────────────────────────────
    task_routes={
        "workers.image_tasks.*": {"queue": "image"},
        "workers.voice_tasks.*": {"queue": "voice"},
        "workers.webhook_tasks.*": {"queue": "webhook"},
        "workers.cleanup_tasks.*": {"queue": "cleanup"},
    },

    # ── Reliability ────────────────────────────────────────────
    task_acks_late=True,               # Job survives worker crash
    worker_prefetch_multiplier=1,      # Only fetch one task at a time
    task_reject_on_worker_lost=True,   # Re-queue if worker dies
    task_track_started=True,           # Track processing state

    # ── Retry defaults ─────────────────────────────────────────
    task_default_retry_delay=10,       # 10 seconds initial delay
    task_max_retries=3,

    # ── Concurrency ────────────────────────────────────────────
    worker_concurrency=2,

    # ── Time limits ────────────────────────────────────────────
    task_soft_time_limit=300,          # 5 min soft limit
    task_time_limit=360,               # 6 min hard kill

    # ── Timezone ───────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,

    # ── Broker settings ────────────────────────────────────────
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": 600,  # 10 min — must be > task_time_limit
    },

    # ── Celery Beat (periodic tasks) ───────────────────────────
    beat_schedule={
        "cleanup-expired-outputs": {
            "task": "workers.cleanup_tasks.cleanup_expired_outputs",
            "schedule": int(os.environ.get("CLEANUP_INTERVAL_MINUTES", 60)) * 60,
            "options": {"queue": "cleanup"},
        },
    },
)

# Auto-discover tasks from workers module
celery_app.autodiscover_tasks(
    [
        "app.workers.image_tasks",
        "app.workers.voice_tasks",
        "app.workers.webhook_tasks",
        "app.workers.cleanup_tasks",
    ],
    related_name=None,
)
