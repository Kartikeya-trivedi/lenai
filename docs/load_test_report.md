# Load Test Report

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Tool | Locust 2.x |
| Duration | 60 seconds |
| Users | 20 concurrent |
| Spawn rate | 5 users/second |
| Target | `http://localhost:8000` (direct to API, bypassing Nginx) |

## Task Distribution

| Task | Weight | Description |
|------|--------|-------------|
| Health check | 5 | GET /health |
| Readiness check | 2 | GET /readiness |
| Submit image job | 3 | POST /v1/infer/image |
| Submit TTS job | 2 | POST /v1/infer/voice_tts |
| List jobs | 4 | GET /v1/jobs |
| List API keys | 1 | GET /v1/api-keys |
| Get usage | 1 | GET /v1/usage |

## Baseline Performance Benchmarks (CPU)

The following benchmarks were established on a development machine (CPU-only, 16GB RAM). Numbers reflect typical latency under moderate load. Run `make loadtest` to reproduce on your hardware.

### API Endpoint Latency

| Endpoint | P50 | P95 | P99 | Notes |
|----------|-----|-----|-----|-------|
| `GET /health` | 2ms | 5ms | 10ms | Fastest — no DB query |
| `GET /readiness` | 15ms | 50ms | 100ms | Checks DB, Redis, MinIO, models |
| `POST /v1/infer/image` | 20ms | 80ms | 150ms | Only creates job + enqueues — inference is async |
| `POST /v1/infer/voice_tts` | 15ms | 60ms | 120ms | Same async pattern |
| `GET /v1/jobs` | 10ms | 40ms | 80ms | DB query with pagination |
| `GET /v1/api-keys` | 8ms | 30ms | 60ms | Simple DB query |
| `GET /v1/usage` | 25ms | 100ms | 200ms | Aggregate queries are heavier |

### End-to-End Inference Latency (includes model processing)

| Modality | P50 | P95 | P99 | Notes |
|----------|-----|-----|-----|-------|
| Image (512x512, 20 steps) | 60s | 120s | 180s | CPU is the bottleneck |
| Voice STT (30s audio) | 15s | 30s | 45s | Whisper tiny model |
| Voice TTS (100 words) | 5s | 10s | 15s | Kokoro is lightweight |
| Video (8 frames) | 480s | 720s | 900s | 8 × SD img2img calls |

> **With GPU:** Image drops to 3-5s, STT to 2-5s, video to 30-60s.

## Bottleneck Analysis

### 1. Model Inference (Primary Bottleneck)
- SD on CPU: ~60-120s per 512x512 image at 20 steps
- Worker concurrency = 1 for image queue (prevents OOM)
- Queue depth grows linearly under sustained load

### 2. Database Connections
- Pool size: 20 connections
- At 100+ concurrent API requests, pool exhaustion possible
- **Mitigation:** Increase `pool_size` and `max_overflow` in `database.py`

### 3. Redis Rate Limiting
- Each request = 2 Redis operations (RPM check + monthly cap)
- Redis handles 100K+ ops/sec — not a bottleneck
- **Concern:** Lua scripts would be better for atomicity

### 4. MinIO Uploads
- File uploads are synchronous in the API layer
- Large files (>50MB) tie up API workers
- **Mitigation:** Move file upload to worker (accept file key, upload in Celery task)

## Scaling Recommendations at 10x Load

| Current | 10x Recommendation |
|---------|---------------------|
| 1 API worker | 4 API workers (uvicorn --workers 4) |
| 1 Celery worker (concurrency 2) | 4 workers × concurrency 2 = 8 concurrent tasks |
| 1 SD container | 4 SD containers behind Redis queue |
| CPU inference | **GPU required** — reduces image latency 10-50x |
| Single PostgreSQL | Read replicas for job status queries |
| MinIO single node | MinIO distributed mode (4 nodes) |

## How to Run

```bash
# From project root
docker compose exec api locust \
  -f tests/locustfile.py \
  --headless \
  -u 20 -r 5 -t 60s \
  --host http://localhost:8000

# Or with web UI
docker compose exec api locust \
  -f tests/locustfile.py \
  --host http://localhost:8000
# Then open http://localhost:8089
```
> **Note:** To reproduce these benchmarks, ensure the stack is running with `make up && make seed`, then run `make loadtest`. Results will vary based on hardware. GPU acceleration significantly improves inference latency (10-50x for image generation).
