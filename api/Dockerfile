# ============================================================
# LenAI API — Production Dockerfile (multi-stage)
# ============================================================
# Stage 1: Builder — install Python deps in a venv
# Stage 2: Runtime — copy venv + app code, run as non-root
# ============================================================

# --------------- Builder Stage ---------------
FROM python:3.11-slim AS builder

# Prevent Python from writing .pyc and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install build-time system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

# Create a virtual environment for clean isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt


# --------------- Runtime Stage ---------------
FROM python:3.11-slim AS runtime

LABEL maintainer="LenAI Team"
LABEL description="LenAI FastAPI media inference API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Defaults — overridden at runtime via .env / docker-compose
    API_WORKERS=1

WORKDIR /app

# Install runtime system deps only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libpq5 \
        curl \
        tini && \
    rm -rf /var/lib/apt/lists/*

# Copy the pre-built venv from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Copy application source
COPY --chown=appuser:appuser . /app

# Copy and set permissions on entrypoint
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Switch to non-root user
USER appuser

EXPOSE 8000

# Use tini as init system for proper signal handling
ENTRYPOINT ["tini", "--"]
CMD ["/app/entrypoint.sh"]
