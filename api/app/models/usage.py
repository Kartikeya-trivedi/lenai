"""
Usage record — metering for billing and dashboard.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class UsageRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    modality: Mapped[str] = mapped_column(String(20), nullable=False)
    compute_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    output_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Relationships
    api_key: Mapped[Optional["ApiKey"]] = relationship(
        "ApiKey", back_populates="usage_records"
    )
    job: Mapped[Optional["Job"]] = relationship(
        "Job", back_populates="usage_records"
    )

    def __repr__(self) -> str:
        return f"<UsageRecord {self.modality} {self.compute_time_ms}ms>"
