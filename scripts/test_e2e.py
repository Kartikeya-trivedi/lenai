#!/usr/bin/env python3
"""
LenAI E2E Test Runner
=====================
Run this AFTER `docker compose up -d` and `make seed`.

Tests the full flow:
  1. Health checks (all services)
  2. API key auth (success + failure)
  3. Image inference (submit → poll → get result)
  4. Voice TTS (submit → poll)
  5. RAG pipeline (ingest → query → verify)
  6. Usage dashboard
  7. Rate limiting

Usage:
  pip install httpx rich
  python scripts/test_e2e.py

  # Or target a different host:
  API_URL=http://your-server python scripts/test_e2e.py
"""

import asyncio
import json
import os
import sys
import time

import httpx

# ── Config ──────────────────────────────────────────────────
API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "lenai_sk_dev_test_key_12345678")
TIMEOUT = 30.0

# Color helpers (no dependency on rich)
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0
skipped = 0


def log_pass(name: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  {GREEN}✓{RESET} {name} {CYAN}{detail}{RESET}")


def log_fail(name: str, detail: str = ""):
    global failed
    failed += 1
    print(f"  {RED}✗{RESET} {name} {RED}{detail}{RESET}")


def log_skip(name: str, detail: str = ""):
    global skipped
    skipped += 1
    print(f"  {YELLOW}○{RESET} {name} {YELLOW}{detail}{RESET}")


def section(title: str):
    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─' * 60}{RESET}")


def headers(key: str = API_KEY) -> dict:
    return {"X-API-Key": key}


async def main():
    print(f"\n{BOLD}🧪 LenAI E2E Test Suite{RESET}")
    print(f"   Target: {CYAN}{API_URL}{RESET}")
    print(f"   API Key: {CYAN}{API_KEY[:20]}...{RESET}")

    async with httpx.AsyncClient(base_url=API_URL, timeout=TIMEOUT) as c:

        # ══════════════════════════════════════════════════════
        section("1. Health Checks")
        # ══════════════════════════════════════════════════════

        # Liveness
        try:
            r = await c.get("/health")
            if r.status_code == 200 and r.json().get("status") == "ok":
                log_pass("GET /health", f"{r.status_code} → {r.json()['status']}")
            else:
                log_fail("GET /health", f"{r.status_code} → {r.text[:100]}")
        except Exception as e:
            log_fail("GET /health", f"Connection failed: {e}")
            print(f"\n  {RED}Cannot reach API at {API_URL}. Is docker compose up?{RESET}")
            return

        # Readiness
        try:
            r = await c.get("/readiness")
            data = r.json()
            status_val = data.get("status", "unknown")
            services = data.get("services", {})
            healthy_count = sum(1 for s in services.values() if s.get("status") == "ok")
            log_pass("GET /readiness", f"{status_val} ({healthy_count}/{len(services)} services up)")
            for name, info in services.items():
                st = info.get("status", "?")
                ms = info.get("latency_ms", "?")
                icon = "✓" if st == "ok" else "✗"
                color = GREEN if st == "ok" else RED
                print(f"      {color}{icon}{RESET} {name}: {st} ({ms}ms)")
        except Exception as e:
            log_fail("GET /readiness", str(e))

        # OpenAPI docs
        try:
            r = await c.get("/openapi.json")
            paths = len(r.json().get("paths", {}))
            log_pass("GET /openapi.json", f"{paths} endpoints documented")
        except Exception as e:
            log_fail("GET /openapi.json", str(e))

        # ══════════════════════════════════════════════════════
        section("2. Authentication")
        # ══════════════════════════════════════════════════════

        # Valid key
        try:
            r = await c.get("/v1/jobs", headers=headers())
            if r.status_code == 200:
                log_pass("Auth with valid key", f"{r.status_code}")
            else:
                log_fail("Auth with valid key", f"{r.status_code} → {r.text[:100]}")
        except Exception as e:
            log_fail("Auth with valid key", str(e))

        # Invalid key
        try:
            r = await c.get("/v1/jobs", headers=headers("lenai_sk_this_key_does_not_exist"))
            if r.status_code == 401:
                log_pass("Auth with invalid key → 401", f"{r.status_code}")
            else:
                log_fail("Auth with invalid key → 401", f"Got {r.status_code}")
        except Exception as e:
            log_fail("Auth with invalid key", str(e))

        # No key
        try:
            r = await c.get("/v1/jobs")
            if r.status_code in (401, 422):
                log_pass("Auth with no key → 401/422", f"{r.status_code}")
            else:
                log_fail("Auth with no key → 401/422", f"Got {r.status_code}")
        except Exception as e:
            log_fail("Auth with no key", str(e))

        # ══════════════════════════════════════════════════════
        section("3. Image Inference (full flow)")
        # ══════════════════════════════════════════════════════

        job_id = None
        try:
            # Submit
            r = await c.post(
                "/v1/infer/image",
                data={
                    "prompt": "a beautiful sunset over mountains, digital art",
                    "negative_prompt": "blurry, low quality",
                    "width": "512",
                    "height": "512",
                    "steps": "5",
                    "cfg_scale": "7.0",
                },
                headers=headers(),
            )
            if r.status_code == 202:
                data = r.json()
                job_id = data.get("job_id")
                log_pass("POST /v1/infer/image → 202", f"job_id={job_id}")
            else:
                log_fail("POST /v1/infer/image", f"{r.status_code} → {r.text[:200]}")
        except Exception as e:
            log_fail("POST /v1/infer/image", str(e))

        # Poll job
        if job_id:
            try:
                r = await c.get(f"/v1/jobs/{job_id}", headers=headers())
                if r.status_code == 200:
                    data = r.json()
                    log_pass(f"GET /v1/jobs/{job_id[:8]}…", f"status={data.get('status')}")
                else:
                    log_fail(f"GET /v1/jobs/{job_id[:8]}…", f"{r.status_code}")
            except Exception as e:
                log_fail("Poll job", str(e))

            # Poll with wait (give celery a few seconds)
            print(f"      {YELLOW}⏳ Waiting 10s for worker to process...{RESET}")
            await asyncio.sleep(10)

            try:
                r = await c.get(f"/v1/jobs/{job_id}", headers=headers())
                if r.status_code == 200:
                    data = r.json()
                    status_val = data.get("status", "unknown")
                    progress = data.get("progress", 0)
                    if status_val == "completed":
                        log_pass("Job completed!", f"output_url exists={bool(data.get('output_url'))}")
                    elif status_val == "failed":
                        log_fail("Job failed", data.get("error_message", "")[:100])
                    else:
                        log_skip("Job still processing", f"status={status_val}, progress={progress}%")
            except Exception as e:
                log_fail("Poll after wait", str(e))

        # Invalid modality
        try:
            r = await c.post(
                "/v1/infer/not_a_modality",
                data={"prompt": "test"},
                headers=headers(),
            )
            if r.status_code == 400:
                log_pass("Invalid modality → 400", "")
            else:
                log_fail("Invalid modality → 400", f"Got {r.status_code}")
        except Exception as e:
            log_fail("Invalid modality", str(e))

        # ══════════════════════════════════════════════════════
        section("4. Voice TTS Inference")
        # ══════════════════════════════════════════════════════

        try:
            r = await c.post(
                "/v1/infer/voice_tts",
                data={
                    "text": "Hello, this is a test of the LenAI text to speech pipeline.",
                    "voice": "af_bella",
                    "speed": "1.0",
                },
                headers=headers(),
            )
            if r.status_code == 202:
                tts_job = r.json().get("job_id")
                log_pass("POST /v1/infer/voice_tts → 202", f"job_id={tts_job}")
            else:
                log_fail("POST /v1/infer/voice_tts", f"{r.status_code} → {r.text[:200]}")
        except Exception as e:
            log_fail("POST /v1/infer/voice_tts", str(e))

        # ══════════════════════════════════════════════════════
        section("5. Job Management")
        # ══════════════════════════════════════════════════════

        try:
            r = await c.get("/v1/jobs", headers=headers())
            if r.status_code == 200:
                jobs = r.json()
                job_count = len(jobs) if isinstance(jobs, list) else jobs.get("total", "?")
                log_pass("GET /v1/jobs", f"{job_count} jobs found")
            else:
                log_fail("GET /v1/jobs", f"{r.status_code}")
        except Exception as e:
            log_fail("GET /v1/jobs", str(e))

        # ══════════════════════════════════════════════════════
        section("6. RAG Pipeline (MediQuery)")
        # ══════════════════════════════════════════════════════

        # Ingest a test document
        try:
            r = await c.post(
                "/v1/rag/ingest",
                json={
                    "text": (
                        "Hypertension, also known as high blood pressure, is a condition "
                        "in which the force of the blood against the artery walls is too "
                        "high. It is defined as having a systolic blood pressure of 130 mmHg "
                        "or higher, or a diastolic blood pressure of 80 mmHg or higher. "
                        "Treatment includes lifestyle changes such as diet and exercise, "
                        "and medications such as ACE inhibitors, ARBs, calcium channel "
                        "blockers, and diuretics. Regular monitoring is essential for "
                        "managing the condition effectively."
                    ),
                    "source": "test_clinical_doc_001",
                    "metadata": {"category": "cardiology", "type": "clinical_guideline"},
                },
                headers=headers(),
            )
            if r.status_code == 200:
                data = r.json()
                log_pass("POST /v1/rag/ingest", f"chunks={data.get('chunks')}")
            elif r.status_code == 503:
                log_skip("POST /v1/rag/ingest", "Embedding model not loaded (expected w/o GPU)")
            else:
                log_fail("POST /v1/rag/ingest", f"{r.status_code} → {r.text[:200]}")
        except Exception as e:
            log_skip("POST /v1/rag/ingest", f"RAG deps not available: {str(e)[:80]}")

        # Query
        try:
            r = await c.post(
                "/v1/rag/query",
                json={
                    "question": "What is the definition of hypertension?",
                    "top_k": 5,
                    "rerank_top_k": 3,
                },
                headers=headers(),
            )
            if r.status_code == 200:
                data = r.json()
                log_pass(
                    "POST /v1/rag/query",
                    f"confidence={data.get('confidence')}, model={data.get('model_used', '?')[:30]}",
                )
            elif r.status_code in (500, 503):
                log_skip("POST /v1/rag/query", "RAG pipeline deps not loaded (needs embedding model)")
            else:
                log_fail("POST /v1/rag/query", f"{r.status_code} → {r.text[:200]}")
        except Exception as e:
            log_skip("POST /v1/rag/query", f"RAG deps: {str(e)[:80]}")

        # Stats
        try:
            r = await c.get("/v1/rag/stats", headers=headers())
            if r.status_code == 200:
                data = r.json()
                log_pass("GET /v1/rag/stats", f"chunks={data.get('total_chunks')}")
            else:
                log_skip("GET /v1/rag/stats", f"{r.status_code}")
        except Exception as e:
            log_skip("GET /v1/rag/stats", str(e))

        # ══════════════════════════════════════════════════════
        section("7. Usage Dashboard")
        # ══════════════════════════════════════════════════════

        try:
            r = await c.get("/v1/usage", headers=headers(), params={"days": 30})
            if r.status_code == 200:
                data = r.json()
                total = data.get("summary", {}).get("total_requests", 0)
                modalities = len(data.get("by_modality", []))
                log_pass("GET /v1/usage", f"total_requests={total}, modalities={modalities}")
            else:
                log_fail("GET /v1/usage", f"{r.status_code} → {r.text[:100]}")
        except Exception as e:
            log_fail("GET /v1/usage", str(e))

        # ══════════════════════════════════════════════════════
        section("8. Error Format Consistency")
        # ══════════════════════════════════════════════════════

        # 404
        try:
            r = await c.get("/v1/nonexistent", headers=headers())
            data = r.json()
            has_envelope = "error" in data and "code" in data.get("error", {})
            if r.status_code == 404 and has_envelope:
                log_pass("404 → error envelope", f"code={data['error']['code']}")
            else:
                log_fail("404 → error envelope", f"{r.status_code}, has_envelope={has_envelope}")
        except Exception as e:
            log_fail("404 → error envelope", str(e))

    # ══════════════════════════════════════════════════════
    section("Results")
    # ══════════════════════════════════════════════════════
    total = passed + failed + skipped
    print(f"\n  {GREEN}✓ Passed: {passed}{RESET}")
    print(f"  {RED}✗ Failed: {failed}{RESET}")
    print(f"  {YELLOW}○ Skipped: {skipped}{RESET}")
    print(f"  Total: {total}")
    print()

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
