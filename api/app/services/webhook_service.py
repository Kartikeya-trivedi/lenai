"""
Webhook dispatch with HMAC signing, retry with exponential backoff, and audit logging.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.webhook_delivery import WebhookDelivery
from app.utils.logging import get_logger
from app.utils.signing import sign_payload

logger = get_logger(__name__)
settings = get_settings()


class WebhookService:
    """Dispatches webhook payloads with signing, retry, and logging."""

    def __init__(self, db: Optional[AsyncSession] = None) -> None:
        self.db = db

    async def dispatch(
        self,
        job_id: uuid.UUID,
        webhook_url: str,
        payload: dict,
        attempt: int = 1,
    ) -> bool:
        """
        POST a signed payload to the webhook URL.
        Returns True if delivery succeeded.
        """
        signature = sign_payload(payload, settings.API_SECRET_KEY)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-LenAI-Event": "job.completed",
            "X-LenAI-Delivery": str(uuid.uuid4()),
        }

        delivery = WebhookDelivery(
            id=uuid.uuid4(),
            job_id=job_id,
            url=webhook_url,
            payload=payload,
            attempt_number=attempt,
        )

        try:
            async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                )

            delivery.status_code = response.status_code
            delivery.response_body = response.text[:2000]  # Truncate long responses

            if response.is_success:
                delivery.delivered_at = datetime.now(timezone.utc)
                logger.info(
                    "webhook_delivered",
                    job_id=str(job_id),
                    url=webhook_url,
                    status_code=response.status_code,
                    attempt=attempt,
                )
            else:
                delivery.error_message = f"HTTP {response.status_code}"
                logger.warning(
                    "webhook_delivery_failed",
                    job_id=str(job_id),
                    status_code=response.status_code,
                    attempt=attempt,
                )

        except httpx.TimeoutException:
            delivery.error_message = "Request timed out"
            logger.warning("webhook_timeout", job_id=str(job_id), attempt=attempt)
        except Exception as e:
            delivery.error_message = str(e)
            logger.error("webhook_error", job_id=str(job_id), error=str(e), attempt=attempt)

        # Record delivery attempt
        if self.db:
            self.db.add(delivery)
            await self.db.flush()

        return delivery.was_successful

    @staticmethod
    def get_retry_delay(attempt: int) -> int:
        """Exponential backoff: 10s, 30s, 90s, 270s, 810s."""
        return min(10 * (3 ** (attempt - 1)), 900)
