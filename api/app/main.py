"""
LenAI — Production Media Inference API Platform.

FastAPI application entry point with lifespan management,
middleware registration, and router mounting.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import dispose_engine
from app.middleware.error_handler import register_error_handlers
from app.middleware.request_logging import RequestLoggingMiddleware
from app.services.model_registry import get_model_registry
from app.services.storage import get_storage
from app.utils.logging import get_logger, configure_logging

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown lifecycle.

    Startup:
      - Initialize structured logging
      - Warm up model registry
      - Ensure MinIO buckets exist
      - Log startup complete

    Shutdown:
      - Drain DB connections
      - Log shutdown
    """
    # ── Startup ────────────────────────────────────────────────
    configure_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
    logger.info("startup_begin", host=settings.API_HOST, port=settings.API_PORT)

    # Warm model registry (loads YAML config)
    registry = get_model_registry()
    model_count = len(registry.get_all_models())
    logger.info("model_registry_loaded", model_count=model_count)

    # Ensure MinIO buckets exist (skip in serverless demo mode)
    import os
    if os.getenv("SKIP_AUTH", "").lower() != "true":
        try:
            storage = get_storage()
            storage.ensure_buckets()
            logger.info("minio_buckets_ready")
        except Exception as exc:
            logger.warning("minio_init_failed", error=str(exc))
    else:
        logger.info("minio_init_skipped_demo_mode")

    logger.info("startup_complete")

    yield

    # ── Shutdown ───────────────────────────────────────────────
    logger.info("shutdown_begin")
    await dispose_engine()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    """Application factory — builds and configures the FastAPI instance."""
    app = FastAPI(
        title="LenAI Media Inference API",
        description=(
            "Unified REST API for image, video, and voice inference "
            "with async job handling, webhook delivery, and usage metering."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware ──────────────────────────────────────────────
    # Order matters: outermost first

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time"],
    )

    # Request logging (adds request_id, logs duration)
    app.add_middleware(RequestLoggingMiddleware)

    # ── Error handlers ─────────────────────────────────────────
    register_error_handlers(app)

    # ── Routers ────────────────────────────────────────────────
    from app.routers import api_keys, health, inference, jobs

    app.include_router(health.router)
    app.include_router(inference.router)
    app.include_router(jobs.router)
    app.include_router(api_keys.router)

    # Conditional routers (only import if module exists)
    try:
        from app.routers import usage
        app.include_router(usage.router)
    except ImportError:
        pass

    try:
        from app.routers import rag
        app.include_router(rag.router)
    except ImportError:
        pass

    return app


# ── App instance ───────────────────────────────────────────────
app = create_app()
