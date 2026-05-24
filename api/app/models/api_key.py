"""
API Key ORM model — authentication, scoping, and rate-limit config per key.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import List, Optional

import bcrypt
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ApiKey(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    key_prefix: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Scopes: ["image", "video", "voice_stt", "voice_tts"]
    scopes: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    # Rate limiting
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    monthly_request_cap: Mapped[int] = mapped_column(
        Integer, default=10000, nullable=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    usage_records: Mapped[List["UsageRecord"]] = relationship(
        "UsageRecord", back_populates="api_key", lazy="selectin"
    )

    def has_scope(self, modality: str) -> bool:
        """Check if this key is allowed for the given modality."""
        if not self.scopes:
            return True  # empty scopes = full access
        return modality in self.scopes

    def verify_key(self, raw_key: str) -> bool:
        """Verify a raw API key against stored hash."""
        return bcrypt.checkpw(raw_key.encode(), self.key_hash.encode())

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """Hash a raw API key for storage."""
        return bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def generate_key() -> str:
        """Generate a new API key in lenai_sk_XXXX format."""
        token = secrets.token_urlsafe(32)
        return f"lenai_sk_{token}"

    def __repr__(self) -> str:
        return f"<ApiKey {self.key_prefix}... [{','.join(self.scopes)}]>"
