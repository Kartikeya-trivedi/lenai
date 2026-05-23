"""
API key management — create, validate, rotate, revoke.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ApiKeyService:
    """CRUD operations for API keys."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_key(
        self,
        tenant_id: uuid.UUID,
        name: str,
        scopes: List[str],
        rate_limit_rpm: int = 60,
        monthly_request_cap: int = 10000,
    ) -> tuple[ApiKey, str]:
        """Create a new API key. Returns (key_model, raw_key)."""
        raw_key = ApiKey.generate_key()
        key_hash = ApiKey.hash_key(raw_key)

        api_key = ApiKey(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            key_hash=key_hash,
            key_prefix=raw_key[:16],
            name=name,
            scopes=scopes,
            rate_limit_rpm=rate_limit_rpm,
            monthly_request_cap=monthly_request_cap,
        )

        self.db.add(api_key)
        await self.db.flush()

        logger.info("api_key_created", key_id=str(api_key.id), name=name)
        return api_key, raw_key

    async def validate_key(self, raw_key: str) -> Optional[ApiKey]:
        """Validate a raw API key and return the model if valid."""
        prefix = raw_key[:16]
        stmt = select(ApiKey).where(
            ApiKey.key_prefix == prefix,
            ApiKey.is_active == True,
            ApiKey.revoked_at == None,
        )
        result = await self.db.execute(stmt)
        candidates = result.scalars().all()

        for key in candidates:
            if key.verify_key(raw_key):
                # Update last_used_at
                key.last_used_at = datetime.now(timezone.utc)
                await self.db.flush()
                return key

        return None

    async def list_keys(self, tenant_id: uuid.UUID) -> List[ApiKey]:
        """List all keys for a tenant (active and revoked)."""
        stmt = (
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id)
            .order_by(ApiKey.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_key(
        self,
        key_id: uuid.UUID,
        tenant_id: uuid.UUID,
        **updates,
    ) -> Optional[ApiKey]:
        """Update an API key's properties."""
        stmt = select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.tenant_id == tenant_id,
        )
        result = await self.db.execute(stmt)
        key = result.scalar_one_or_none()

        if key is None:
            return None

        for field, value in updates.items():
            if value is not None and hasattr(key, field):
                setattr(key, field, value)

        await self.db.flush()
        logger.info("api_key_updated", key_id=str(key_id))
        return key

    async def revoke_key(
        self,
        key_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Optional[ApiKey]:
        """Soft-revoke an API key."""
        stmt = select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.tenant_id == tenant_id,
        )
        result = await self.db.execute(stmt)
        key = result.scalar_one_or_none()

        if key is None:
            return None

        key.is_active = False
        key.revoked_at = datetime.now(timezone.utc)
        await self.db.flush()

        logger.info("api_key_revoked", key_id=str(key_id))
        return key

    async def rotate_key(
        self,
        key_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> tuple[Optional[ApiKey], str]:
        """Rotate: revoke old key and issue a new one with same config."""
        old_key = await self.revoke_key(key_id, tenant_id)
        if old_key is None:
            return None, ""

        new_key, raw_key = await self.create_key(
            tenant_id=tenant_id,
            name=f"{old_key.name} (rotated)",
            scopes=old_key.scopes,
            rate_limit_rpm=old_key.rate_limit_rpm,
            monthly_request_cap=old_key.monthly_request_cap,
        )

        logger.info("api_key_rotated", old_key_id=str(key_id), new_key_id=str(new_key.id))
        return new_key, raw_key
