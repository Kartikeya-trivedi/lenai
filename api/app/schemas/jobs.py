"""
Pydantic schemas for job status and listing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Single job status response."""

    id: uuid.UUID
    modality: str
    status: str
    progress: int = Field(ge=0, le=100)
    input_params: Optional[Dict[str, Any]] = None
    output_url: Optional[str] = None
    output_data: Optional[Dict[str, Any]] = None
    output_url_expires_at: Optional[datetime] = None
    error_message: Optional[str] = None
    webhook_url: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Paginated job list response."""

    items: List[JobResponse]
    total: int
    page: int
    per_page: int
    pages: int


class JobFilters(BaseModel):
    """Filters for job listing."""

    status: Optional[str] = None
    modality: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
