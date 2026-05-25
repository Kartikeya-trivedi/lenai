"""
Global exception handler — ensures EVERY error returns a consistent ErrorResponse envelope.
No stack traces leak to clients; they are logged server-side.
"""

from __future__ import annotations

import traceback
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorDetail, ErrorResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ModelUnavailableError(Exception):
    """Raised when a model container is not healthy."""

    def __init__(self, modality: str, detail: str = ""):
        self.modality = modality
        self.detail = detail
        super().__init__(f"Model for {modality} is unavailable: {detail}")


class QuotaExceededError(Exception):
    """Raised when rate limit or monthly cap is exceeded."""

    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded")


def _build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach exception handlers to the FastAPI app."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.warning(
            "validation_error",
            request_id=request_id,
            errors=exc.errors(),
        )
        return _build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": exc.errors()},
            request_id=request_id,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return _build_error_response(
            status_code=exc.status_code,
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            request_id=request_id,
        )

    @app.exception_handler(ModelUnavailableError)
    async def model_unavailable_handler(
        request: Request, exc: ModelUnavailableError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.error(
            "model_unavailable",
            modality=exc.modality,
            detail=exc.detail,
            request_id=request_id,
        )
        return _build_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="MODEL_UNAVAILABLE",
            message=f"Model for '{exc.modality}' is currently unavailable",
            details={"modality": exc.modality},
            request_id=request_id,
        )

    @app.exception_handler(QuotaExceededError)
    async def quota_exceeded_handler(
        request: Request, exc: QuotaExceededError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        response = _build_error_response(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMIT_EXCEEDED",
            message="Rate limit or quota exceeded",
            details={"retry_after": exc.retry_after},
            request_id=request_id,
        )
        response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.error(
            "unhandled_exception",
            request_id=request_id,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return _build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message=str(exc),
            details={"traceback": traceback.format_exc()},
            request_id=request_id,
        )
