"""
Webhook delivery Celery task — HMAC-signed POST with exponential backoff retry.

Every delivery attempt is logged in the WebhookDelivery table.
After max retries, the delivery is marked as failed (does not affect job status).
"""

from __future__ import annotations

import json
import time
import traceback
import uuid

import httpx

from app.workers.celery_app import celery_app
from app.workers.image_tasks import _get_job, _get_sync_session
from app.config import get_settings
from app.utils.logging import get_logger
from app.utils.signing import sign_payload

logger = get_logger(__name__)
settings = get_settings()

# Retry delays: 10s, 30s, 90s, 270s, 810s (exponential backoff)
RETRY_DELAYS = [10, 30, 90, 270, 810]


@celery_app.task(
    name="workers.webhook_tasks.deliver_webhook",
    bind=True,
    max_retries=5,
    acks_late=True,
    soft_time_limit=60,
    time_limit=90,
)
def deliver_webhook(self, job_id: str, webhook_url: str, event: str = "job.completed"):
    """
    Deliver a signed webhook payload to the configured URL.

    Headers:
      - X-Webhook-Signature: HMAC-SHA256 of the payload body
      - X-LenAI-Event: Event type (job.completed, job.failed, etc.)
      - X-LenAI-Delivery: Unique delivery ID for idempotency
      - Content-Type: application/json
    """
    delivery_id = str(uuid.uuid4())
    attempt = self.request.retries + 1

    logger.info(
        "webhook_delivery_started",
        job_id=job_id,
        webhook_url=webhook_url,
        event=event,
        attempt=attempt,
        delivery_id=delivery_id,
    )

    # Build payload
    job = _get_job(job_id)
    payload = {
        "event": event,
        "delivery_id": delivery_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": {
            "job_id": job_id,
            "status": job.status if job else "unknown",
            "modality": job.modality if job else "unknown",
            "output_url": job.output_url if job else None,
            "error_message": job.error_message if job and job.status in ("failed", "dead_letter") else None,
        },
    }

    payload_json = json.dumps(payload, sort_keys=True)

    # Sign payload
    signature = sign_payload(payload, settings.API_SECRET_KEY)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-LenAI-Event": event,
        "X-LenAI-Delivery": delivery_id,
        "User-Agent": "LenAI-Webhook/1.0",
    }

    status_code = None
    response_body = None
    error_message = None

    try:
        with httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
            response = client.post(
                webhook_url,
                content=payload_json,
                headers=headers,
            )
            status_code = response.status_code
            response_body = response.text[:1000]  # Truncate to prevent huge storage

        # Log the delivery attempt
        _log_delivery(
            job_id=job_id,
            delivery_id=delivery_id,
            url=webhook_url,
            payload=payload,
            status_code=status_code,
            response_body=response_body,
            attempt=attempt,
        )

        # Consider 2xx as success
        if 200 <= status_code < 300:
            logger.info(
                "webhook_delivered",
                job_id=job_id,
                delivery_id=delivery_id,
                status_code=status_code,
            )
            return

        # Non-2xx — retry
        logger.warning(
            "webhook_non_2xx",
            job_id=job_id,
            status_code=status_code,
            attempt=attempt,
        )
        raise RuntimeError(f"Webhook returned {status_code}")

    except httpx.TimeoutException as exc:
        error_message = f"Timeout after {settings.WEBHOOK_TIMEOUT_SECONDS}s"
        logger.warning("webhook_timeout", job_id=job_id, attempt=attempt)

        _log_delivery(
            job_id=job_id,
            delivery_id=delivery_id,
            url=webhook_url,
            payload=payload,
            status_code=None,
            response_body=None,
            attempt=attempt,
            error_message=error_message,
        )

        retry_delay = RETRY_DELAYS[min(self.request.retries, len(RETRY_DELAYS) - 1)]
        raise self.retry(exc=exc, countdown=retry_delay)

    except httpx.ConnectError as exc:
        error_message = f"Connection failed: {str(exc)}"
        logger.warning("webhook_connection_error", job_id=job_id, attempt=attempt)

        _log_delivery(
            job_id=job_id,
            delivery_id=delivery_id,
            url=webhook_url,
            payload=payload,
            status_code=None,
            response_body=None,
            attempt=attempt,
            error_message=error_message,
        )

        retry_delay = RETRY_DELAYS[min(self.request.retries, len(RETRY_DELAYS) - 1)]
        raise self.retry(exc=exc, countdown=retry_delay)

    except self.MaxRetriesExceededError:
        logger.error(
            "webhook_max_retries_exceeded",
            job_id=job_id,
            webhook_url=webhook_url,
            total_attempts=attempt,
        )
        # Final failure — log but don't affect job status

    except Exception as exc:
        error_message = str(exc)
        error_trace = traceback.format_exc()
        logger.error(
            "webhook_delivery_error",
            job_id=job_id,
            error=error_message,
            attempt=attempt,
        )

        _log_delivery(
            job_id=job_id,
            delivery_id=delivery_id,
            url=webhook_url,
            payload=payload,
            status_code=status_code,
            response_body=response_body,
            attempt=attempt,
            error_message=error_message,
        )

        if self.request.retries < self.max_retries:
            retry_delay = RETRY_DELAYS[min(self.request.retries, len(RETRY_DELAYS) - 1)]
            raise self.retry(exc=exc, countdown=retry_delay)


def _log_delivery(
    job_id: str,
    delivery_id: str,
    url: str,
    payload: dict,
    status_code: int | None,
    response_body: str | None,
    attempt: int,
    error_message: str | None = None,
):
    """Persist webhook delivery attempt to the database."""
    from datetime import datetime, timezone
    from app.models.webhook_delivery import WebhookDelivery

    session = _get_sync_session()
    try:
        delivery = WebhookDelivery(
            id=uuid.UUID(delivery_id),
            job_id=uuid.UUID(job_id),
            url=url,
            payload=payload,
            status_code=status_code,
            response_body=response_body,
            attempt_number=attempt,
            error_message=error_message,
            delivered_at=datetime.now(timezone.utc) if status_code and 200 <= status_code < 300 else None,
        )
        session.add(delivery)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("webhook_delivery_log_failed", delivery_id=delivery_id, error=str(exc))
    finally:
        session.close()
