"""
Pydantic schemas — common types used across all endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Consistent error detail payload."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional context about the error"
    )
    request_id: Optional[str] = Field(
        default=None, description="Request ID for tracing"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now().astimezone()
    )


class ErrorResponse(BaseModel):
    """Consistent error envelope — every error response uses this shape."""

    error: ErrorDetail


class PaginationParams(BaseModel):
    """Query params for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Overall status: ok | degraded | unhealthy")
    version: str = Field(default="1.0.0")
    services: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-service health status",
    )


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
