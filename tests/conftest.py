"""
Pytest fixtures and test configuration for LenAI API tests.

Uses FastAPI's dependency_overrides for clean mocking.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Override settings before importing app modules
os.environ.update({
    "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
    "REDIS_URL": "redis://localhost:6379/1",
    "MINIO_ENDPOINT": "localhost:9000",
    "API_SECRET_KEY": "test_secret_key_at_least_32_chars_long",
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "console",
})


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for all tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Shared mock objects ──────────────────────────────────────

@pytest.fixture
def test_tenant_id():
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def test_api_key_id():
    return uuid.UUID("abcdef01-2345-6789-abcd-ef0123456789")


@pytest.fixture
def test_api_key_raw():
    return "lenai_sk_test1234567890abcdef"


@pytest.fixture
def mock_api_key(test_tenant_id, test_api_key_id):
    """A mock ApiKey object for dependency override."""
    key = MagicMock()
    key.id = test_api_key_id
    key.tenant_id = test_tenant_id
    key.key_prefix = "lenai_sk_test12"
    key.name = "test-key"
    key.scopes = ["image", "voice_stt", "voice_tts"]
    key.rate_limit_rpm = 60
    key.monthly_request_cap = 10000
    key.is_active = True
    key.last_used_at = datetime.now(timezone.utc)
    key.has_scope.return_value = True
    key.verify_key.return_value = True
    return key


# ── Service mocks ────────────────────────────────────────────

@pytest.fixture
def mock_storage():
    """Mock MinIO storage service."""
    with patch("app.services.storage.get_storage") as mock:
        storage = MagicMock()
        storage.upload_file.return_value = None
        storage.generate_presigned_url.return_value = "http://minio:9000/test/file.png"
        storage.ensure_buckets.return_value = None
        storage.check_health.return_value = (True, 1.0)
        mock.return_value = storage
        yield storage


@pytest.fixture
def mock_redis():
    """Mock Redis for rate limiting."""
    with patch("app.middleware.rate_limiter.get_redis") as mock:
        redis = AsyncMock()
        redis.get.return_value = None
        redis.incr.return_value = 1
        redis.expire.return_value = True
        redis.ttl.return_value = 60
        redis.ping.return_value = True
        pipe = AsyncMock()
        pipe.incr.return_value = None
        pipe.expire.return_value = None
        pipe.execute.return_value = [1, True]
        redis.pipeline.return_value = pipe
        mock.return_value = redis
        yield redis


@pytest.fixture
def mock_model_registry():
    """Mock model registry."""
    with patch("app.services.model_registry.get_model_registry") as mock:
        registry = MagicMock()
        registry.get_model_config.return_value = MagicMock(
            modality="image",
            endpoint="http://sd:7860",
            max_concurrent=1,
        )
        registry.get_all_models.return_value = [
            MagicMock(modality="image", name="stable-diffusion"),
            MagicMock(modality="voice_stt", name="whisper"),
            MagicMock(modality="voice_tts", name="kokoro"),
        ]
        registry.check_model_health = AsyncMock(return_value=(True, 10.0))
        mock.return_value = registry
        yield registry


@pytest.fixture
def mock_celery():
    """Mock Celery to prevent actual task enqueue."""
    with patch("app.workers.celery_app.celery_app") as mock_app:
        mock_result = MagicMock()
        mock_result.id = str(uuid.uuid4())
        mock_app.send_task.return_value = mock_result
        yield mock_app


# ── App and client fixtures ──────────────────────────────────

@pytest_asyncio.fixture
async def app(
    mock_celery,
    mock_storage,
    mock_redis,
    mock_model_registry,
    mock_api_key,
):
    """Create a test FastAPI app with dependency overrides."""
    from app.dependencies import get_current_api_key
    from app.main import create_app

    test_app = create_app()

    # Override auth dependency to return our mock key
    test_app.dependency_overrides[get_current_api_key] = lambda: mock_api_key

    yield test_app

    # Cleanup overrides
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    """Create an async HTTP client (no auth header needed for health)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def unauthenticated_app(
    mock_celery,
    mock_storage,
    mock_redis,
    mock_model_registry,
):
    """Create a test app WITHOUT auth override (for testing auth failures)."""
    from app.main import create_app

    test_app = create_app()
    yield test_app


@pytest_asyncio.fixture
async def unauthenticated_client(unauthenticated_app):
    """Client without auth — for testing 401/422 responses."""
    transport = ASGITransport(app=unauthenticated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
