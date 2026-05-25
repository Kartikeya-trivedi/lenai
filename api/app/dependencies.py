"""
FastAPI dependencies — authentication, rate limiting, and shared deps.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.error_handler import QuotaExceededError
from app.middleware.rate_limiter import check_rate_limit
from app.models.api_key import ApiKey
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def get_current_api_key(
    x_api_key: str = Header(..., alias="X-API-Key", description="API key for authentication"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """
    Validate the X-API-Key header and return the associated ApiKey model.

    Steps:
      1. Extract key prefix (first 8 chars after 'lenai_sk_')
      2. Look up all active keys matching that prefix
      3. Verify bcrypt hash against the full key
      4. Check rate limits (RPM + monthly cap)
      5. Update last_used_at timestamp
      6. Return the authenticated ApiKey

    Raises:
      HTTPException 401: invalid or revoked key
      QuotaExceededError: rate limit exceeded
    """
    import os
    # Allow bypassing auth for serverless deployments without a DB
    if os.getenv("SKIP_AUTH", "").lower() == "true":
        # Return a mock ApiKey-like object with full access
        class MockKey:
            def __init__(self):
                self.id = uuid.uuid4()
                self.tenant_id = uuid.uuid4()
                self.key_prefix = "demo_key"
                self.name = "demo"
                self.scopes = ["image", "voice_stt", "voice_tts"]
                self.is_active = True
                self.rate_limit_rpm = 9999
                self.monthly_request_cap = 99999
            
            def has_scope(self, scope: str) -> bool:
                return True
                
        return MockKey()

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    # Extract prefix for DB lookup
    # Key format: lenai_sk_XXXXXXXX...
    prefix = x_api_key[:16] if len(x_api_key) >= 16 else x_api_key

    # Look up candidate keys by prefix
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_prefix == prefix[:16],
            ApiKey.is_active.is_(True),
            ApiKey.revoked_at.is_(None),
        )
    )
    candidates = result.scalars().all()

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Verify hash against candidates
    authenticated_key = None
    for candidate in candidates:
        if candidate.verify_key(x_api_key):
            authenticated_key = candidate
            break

    if authenticated_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Check rate limits
    allowed, retry_after = await check_rate_limit(
        api_key_id=str(authenticated_key.id),
        rpm_limit=authenticated_key.rate_limit_rpm or settings.DEFAULT_RATE_LIMIT_RPM,
        monthly_cap=authenticated_key.monthly_request_cap or settings.DEFAULT_MONTHLY_CAP,
    )
    if not allowed:
        raise QuotaExceededError(retry_after=retry_after)

    # Update last_used_at
    from datetime import datetime, timezone

    authenticated_key.last_used_at = datetime.now(timezone.utc)

    logger.debug(
        "api_key_authenticated",
        key_prefix=authenticated_key.key_prefix,
        tenant_id=str(authenticated_key.tenant_id),
    )

    return authenticated_key
