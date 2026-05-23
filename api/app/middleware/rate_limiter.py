"""
Token-bucket rate limiter backed by Redis.
Enforces per-key RPM limits and monthly request caps.
"""

from __future__ import annotations

import time
from typing import Optional

import redis.asyncio as aioredis

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

settings = get_settings()

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Lazy singleton Redis connection."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
    return _redis


async def check_rate_limit(
    api_key_id: str,
    rpm_limit: int,
    monthly_cap: int,
) -> tuple[bool, int]:
    """
    Check if the request is within rate limits.

    Returns:
        (allowed: bool, retry_after_seconds: int)
    """
    r = await get_redis()

    # ── Per-minute token bucket ────────────────────────────────
    minute_key = f"ratelimit:{api_key_id}:rpm"
    current_count = await r.get(minute_key)

    if current_count is not None and int(current_count) >= rpm_limit:
        ttl = await r.ttl(minute_key)
        logger.warning(
            "rate_limit_exceeded",
            api_key_id=api_key_id,
            limit=rpm_limit,
            retry_after=max(ttl, 1),
        )
        return False, max(ttl, 1)

    pipe = r.pipeline()
    pipe.incr(minute_key)
    pipe.expire(minute_key, 60, nx=True)
    await pipe.execute()

    # ── Monthly cap ────────────────────────────────────────────
    month_key = f"ratelimit:{api_key_id}:monthly:{time.strftime('%Y-%m')}"
    monthly_count = await r.get(month_key)

    if monthly_count is not None and int(monthly_count) >= monthly_cap:
        logger.warning(
            "monthly_cap_exceeded",
            api_key_id=api_key_id,
            cap=monthly_cap,
        )
        # Retry after ~1 day (rough, resets at month boundary)
        return False, 86400

    pipe = r.pipeline()
    pipe.incr(month_key)
    pipe.expire(month_key, 31 * 86400, nx=True)  # TTL: ~1 month
    await pipe.execute()

    return True, 0


async def get_remaining_quota(api_key_id: str, monthly_cap: int) -> int:
    """Get remaining monthly quota for an API key."""
    r = await get_redis()
    month_key = f"ratelimit:{api_key_id}:monthly:{time.strftime('%Y-%m')}"
    current = await r.get(month_key)
    if current is None:
        return monthly_cap
    return max(0, monthly_cap - int(current))


async def check_redis_health() -> tuple[bool, float]:
    """Ping Redis and return (healthy, latency_ms)."""
    start = time.monotonic()
    try:
        r = await get_redis()
        await r.ping()
        latency = (time.monotonic() - start) * 1000
        return True, round(latency, 2)
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return False, round(latency, 2)
