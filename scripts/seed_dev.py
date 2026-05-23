"""
Seed development data — creates test API keys and sample jobs.

Usage:
  python -m scripts.seed_dev
  # or via Makefile:
  make seed
"""

import asyncio
import uuid
from datetime import datetime, timezone

from app.config import get_settings
from app.database import async_session_factory
from app.models.api_key import ApiKey
from app.models.job import Job, JobStatus, Modality


async def seed():
    """Seed development database with test data."""
    settings = get_settings()

    async with async_session_factory() as session:
        # ── Test API Keys ──────────────────────────────────────
        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        # Development key with all scopes
        dev_key_raw = "lenai_sk_dev_test_key_12345678"
        dev_key = ApiKey(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            key_hash=ApiKey.hash_key(dev_key_raw),
            key_prefix=dev_key_raw[:16],
            name="Development Key",
            scopes=["image", "voice_stt", "voice_tts", "video"],
            rate_limit_rpm=120,
            monthly_request_cap=100000,
            is_active=True,
        )
        session.add(dev_key)

        # Limited key (image only)
        limited_key_raw = "lenai_sk_limited_images_only_1"
        limited_key = ApiKey(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            key_hash=ApiKey.hash_key(limited_key_raw),
            key_prefix=limited_key_raw[:16],
            name="Image-Only Key",
            scopes=["image"],
            rate_limit_rpm=10,
            monthly_request_cap=100,
            is_active=True,
        )
        session.add(limited_key)

        # ── Sample Jobs ────────────────────────────────────────
        for i, (modality, status) in enumerate([
            (Modality.IMAGE.value, JobStatus.COMPLETED.value),
            (Modality.IMAGE.value, JobStatus.FAILED.value),
            (Modality.VOICE_STT.value, JobStatus.COMPLETED.value),
            (Modality.VOICE_TTS.value, JobStatus.PROCESSING.value),
            (Modality.IMAGE.value, JobStatus.DEAD_LETTER.value),
        ]):
            job = Job(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                api_key_id=dev_key.id,
                modality=modality,
                status=status,
                input_params={"prompt": f"Test prompt {i}", "webhook_url": None},
                progress=100 if status == "completed" else 50 if status == "processing" else 0,
                error_message="Model timeout" if status in ("failed", "dead_letter") else None,
            )
            session.add(job)

        await session.commit()

    print("✅ Development data seeded successfully!")
    print(f"   Dev API Key: {dev_key_raw}")
    print(f"   Limited Key: {limited_key_raw}")
    print(f"   Tenant ID:   {tenant_id}")


if __name__ == "__main__":
    asyncio.run(seed())
