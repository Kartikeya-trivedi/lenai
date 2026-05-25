# ============================================================
# LenAI Celery Worker — Production Dockerfile (multi-stage)
# ============================================================
# Shares the same dependency set as the API image, but runs
# the Celery worker process instead of Uvicorn.
# ============================================================

# --------------- Builder Stage ---------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Use the same requirements as the API
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt


# --------------- Runtime Stage ---------------
FROM python:3.11-slim AS runtime

LABEL maintainer="LenAI Team"
LABEL description="LenAI Celery background worker"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    CELERY_CONCURRENCY=2

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tini && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Copy the same application code (workers live inside api/app/workers/)
COPY --chown=appuser:appuser . /app

# NOTE: entrypoint.sh is bind-mounted at runtime by docker-compose
# (worker/entrypoint.sh -> /app/entrypoint.sh)

USER appuser

# Celery worker doesn't expose ports but we keep a health signal
ENTRYPOINT ["tini", "--"]
CMD ["/app/entrypoint.sh"]
