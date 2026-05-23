"""
Pydantic schemas for API key management.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    """Create a new API key."""

    name: str = Field(..., min_length=1, max_length=255, description="Key name")
    scopes: List[str] = Field(
        default_factory=lambda: ["image", "voice_stt", "voice_tts", "video"],
        description="Allowed modalities",
    )
    rate_limit_rpm: int = Field(default=60, ge=1, le=10000, description="Requests per minute")
    monthly_request_cap: int = Field(
        default=10000, ge=1, description="Monthly request limit"
    )


class ApiKeyResponse(BaseModel):
    """API key info (key is masked)."""

    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: List[str]
    rate_limit_rpm: int
    monthly_request_cap: int
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned only on creation — includes the raw key (shown once)."""

    raw_key: str = Field(
        ..., description="Full API key — save this now, it will not be shown again"
    )


class UpdateApiKeyRequest(BaseModel):
    """Partial update for an API key."""

    name: Optional[str] = Field(default=None, max_length=255)
    scopes: Optional[List[str]] = None
    rate_limit_rpm: Optional[int] = Field(default=None, ge=1, le=10000)
    monthly_request_cap: Optional[int] = Field(default=None, ge=1)


class RotateKeyResponse(BaseModel):
    """Response after rotating an API key."""

    new_key: str
    old_key_revoked_at: datetime
