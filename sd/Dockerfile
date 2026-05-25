# ============================================================
# LenAI SD — Lightweight Stable Diffusion Server
# ============================================================
# Uses HuggingFace diffusers instead of AUTOMATIC1111 for a
# lighter footprint. CPU by default; GPU via docker-compose.gpu.yml.
# ============================================================

FROM python:3.10-slim

LABEL maintainer="LenAI Team"
LABEL description="Lightweight Stable Diffusion inference server"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SD_MODEL_ID=runwayml/stable-diffusion-v1-5 \
    SD_MODEL_CACHE=/models \
    TRANSFORMERS_CACHE=/models \
    HF_HOME=/models

WORKDIR /app

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        tini && \
    rm -rf /var/lib/apt/lists/*

# Python deps
RUN pip install --no-cache-dir \
    torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    diffusers[torch]>=0.27.0 \
    transformers>=4.38.0 \
    accelerate>=0.27.0 \
    safetensors>=0.4.0 \
    fastapi>=0.115.0 \
    uvicorn[standard]>=0.30.0 \
    pillow>=10.0 \
    pydantic>=2.0

# Non-root user
RUN groupadd --gid 1000 sduser && \
    useradd --uid 1000 --gid sduser --shell /bin/bash --create-home sduser && \
    mkdir -p /models && chown sduser:sduser /models

COPY --chown=sduser:sduser server.py /app/server.py

USER sduser

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -sf http://localhost:7860/sdapi/v1/options || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
