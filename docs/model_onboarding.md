# Model Onboarding Guide

How to add a new inference model to the LenAI platform.

---

## Overview

The platform uses a **config-driven model registry** (`api/model_registry.yaml`). Adding a new model requires:

1. A Docker container running the model with an HTTP API
2. A YAML entry in `model_registry.yaml`
3. A Celery task handler for the new modality (if it's a new modality)

**Zero code changes required for adding a model to an existing modality.**

---

## Step-by-Step: Adding a New Model

### Step 1: Prepare the Model Container

Your model container must expose:
- **An HTTP API** (REST) that accepts inference requests
- **A health check endpoint** (GET) that returns 200 when ready

Example for a custom model:
```python
# model_server.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/predict")
def predict(request: dict):
    # Run inference
    result = model.predict(request["input"])
    return {"output": result}
```

### Step 2: Add Docker Compose Service

```yaml
# docker-compose.yml
services:
  my-new-model:
    build: ./my_model
    ports:
      - "8890:8890"
    networks:
      - model_net
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8890/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    restart: unless-stopped
```

### Step 3: Add Model Registry Entry

```yaml
# api/model_registry.yaml
models:
  my-new-model:
    modality: custom_modality    # or existing: image, voice_stt, voice_tts
    endpoint: http://my-new-model:8890
    health_check: /health
    input_schema:
      input_field:
        type: string
        required: true
        max_length: 5000
    output_format: json
    max_concurrent: 2
    timeout_seconds: 120
    resource_limits:
      cpu: "2.0"
      memory: "4G"
```

### Step 4: Add Celery Task (new modality only)

If this is a **new modality** (not image/voice_stt/voice_tts), create a new task file:

```python
# api/app/workers/custom_tasks.py
from app.workers.celery_app import celery_app
from app.workers.image_tasks import _get_job, _update_job_status, _record_usage

@celery_app.task(name="workers.custom_tasks.process_custom", bind=True, max_retries=3)
def process_custom(self, job_id: str):
    # 1. Update status
    _update_job_status(job_id, "processing")
    
    # 2. Get job params
    job = _get_job(job_id)
    
    # 3. Call model API
    # 4. Store result in MinIO
    # 5. Update job to completed
    # 6. Record usage
    pass
```

Then add the task mapping in `api/app/services/inference.py`:
```python
task_map = {
    ...
    "custom_modality": "workers.custom_tasks.process_custom",
}
```

### Step 5: Restart

```bash
docker compose up -d --build
```

---

## Zero-Downtime Onboarding

For production deployments:

1. Start the new model container separately
2. Verify health: `curl http://model:port/health`
3. Add the YAML entry
4. Rolling restart of API: `docker compose up -d --no-deps api`
5. Rolling restart of workers: `docker compose up -d --no-deps worker`

The model registry reloads on startup, so running containers pick up the new config.

---

## Config Reference

| Field | Type | Description |
|-------|------|-------------|
| `modality` | string | Which inference type (must match `Modality` enum) |
| `endpoint` | string | Internal Docker network URL |
| `health_check` | string | GET path returning 200 when ready |
| `input_schema` | object | Validation rules per parameter |
| `output_format` | string | Expected output type (png, json, mp3, mp4) |
| `max_concurrent` | int | Max parallel requests to this model |
| `timeout_seconds` | int | Per-request timeout |
| `resource_limits` | object | Docker resource hints (cpu, memory) |

### Input Schema Types

| Type | Options |
|------|---------|
| `string` | `required`, `max_length`, `default`, `options` (enum) |
| `integer` | `required`, `default`, `min`, `max` |
| `float` | `required`, `default`, `min`, `max` |
| `file` | `required`, `max_size_mb`, `formats` (array) |
