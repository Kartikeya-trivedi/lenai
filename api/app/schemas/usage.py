"""
Pydantic schemas for usage dashboard and metering.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class UsageSummary(BaseModel):
    """Aggregated usage summary."""

    total_requests: int = 0
    total_errors: int = 0
    total_compute_ms: int = 0
    total_storage_bytes: int = 0
    quota_remaining: int = 0


class UsageByModality(BaseModel):
    """Usage breakdown per modality."""

    modality: str
    request_count: int = 0
    avg_latency_ms: float = 0.0
    error_count: int = 0
    total_compute_ms: int = 0


class DailyUsage(BaseModel):
    """Single day usage data point."""

    date: date
    request_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0


class UsageDashboardResponse(BaseModel):
    """Full dashboard response."""

    summary: UsageSummary
    by_modality: List[UsageByModality]
    daily: List[DailyUsage]


class UsageFilters(BaseModel):
    """Filters for usage queries."""

    api_key_id: Optional[str] = None
    modality: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    days: int = Field(default=30, ge=1, le=365)
