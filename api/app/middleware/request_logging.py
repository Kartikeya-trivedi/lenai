"""
Structured request/response logging middleware.
Every request gets a unique request_id propagated through the system.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.utils.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with structured fields for observability."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.monotonic()

        # Extract API key prefix if present
        api_key_header = request.headers.get("X-API-Key", "")
        key_prefix = api_key_header[:12] + "..." if api_key_header else "none"

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            logger.error(
                "request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client else "unknown",
                api_key_prefix=key_prefix,
                error=str(exc),
            )
            raise

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)

        # Skip noisy health check logs
        if request.url.path not in ("/health", "/readiness"):
            logger.info(
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client else "unknown",
                api_key_prefix=key_prefix,
            )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response
