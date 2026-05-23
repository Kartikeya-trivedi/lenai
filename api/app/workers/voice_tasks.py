"""
Voice inference Celery tasks — Whisper STT and Kokoro TTS.

STT flow:
  1. Download audio from MinIO → POST to Whisper /asr → store transcript in MinIO
TTS flow:
  1. POST text to Kokoro /v1/audio/speech → store audio file in MinIO → presigned URL
"""

from __future__ import annotations

import io
import time
import traceback
import uuid

import httpx

from app.workers.celery_app import celery_app
from app.workers.image_tasks import (
    _get_job,
    _get_sync_session,
    _record_usage,
    _update_job_status,
)
from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@celery_app.task(
    name="workers.voice_tasks.transcribe_audio",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    acks_late=True,
)
def transcribe_audio(self, job_id: str):
    """
    Speech-to-text transcription via Whisper ASR service.

    Downloads audio from MinIO, sends to Whisper /asr endpoint,
    stores transcript JSON in MinIO outputs bucket.
    """
    logger.info("stt_task_started", job_id=job_id, attempt=self.request.retries + 1)
    start_time = time.monotonic()

    _update_job_status(job_id, "processing", progress=10)

    job = _get_job(job_id)
    if not job:
        logger.error("job_not_found", job_id=job_id)
        return

    params = job.input_params or {}

    try:
        from app.services.storage import get_storage
        import json

        storage = get_storage()

        # 1. Download audio file from MinIO
        if not job.input_file_key:
            raise ValueError("No input audio file provided for STT job")

        audio_data = storage.download_file(
            bucket=settings.MINIO_BUCKET_INPUTS,
            key=job.input_file_key,
        )

        _update_job_status(job_id, "processing", progress=30)

        # 2. Send to Whisper ASR
        # Determine filename from key
        filename = job.input_file_key.split("/")[-1] if "/" in job.input_file_key else "audio.wav"

        with httpx.Client(timeout=600.0) as client:
            files = {"audio_file": (filename, io.BytesIO(audio_data), "audio/wav")}
            whisper_params = {
                "task": "transcribe",
                "output": "json",
            }
            language = params.get("language")
            if language:
                whisper_params["language"] = language

            response = client.post(
                f"{settings.WHISPER_API_URL}/asr",
                files=files,
                params=whisper_params,
            )

        _update_job_status(job_id, "processing", progress=70)

        if response.status_code != 200:
            raise RuntimeError(
                f"Whisper API returned {response.status_code}: {response.text[:500]}"
            )

        # 3. Parse transcript result
        transcript = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"text": response.text}

        # 4. Store transcript in MinIO
        transcript_json = json.dumps(transcript, ensure_ascii=False, indent=2)
        output_key = f"voice_stt/{job_id}/transcript.json"

        storage.upload_file(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=output_key,
            data=transcript_json.encode("utf-8"),
            content_type="application/json",
        )

        _update_job_status(job_id, "processing", progress=85)

        # 5. Generate presigned URL
        output_url = storage.generate_presigned_url(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=output_key,
            ttl_hours=settings.OUTPUT_URL_TTL_HOURS,
        )

        # 6. Mark completed
        compute_ms = int((time.monotonic() - start_time) * 1000)
        _update_job_status(
            job_id,
            "completed",
            progress=100,
            output_file_key=output_key,
            output_url=output_url,
        )

        logger.info(
            "stt_task_completed",
            job_id=job_id,
            compute_time_ms=compute_ms,
        )

        _record_usage(job_id, "voice_stt", compute_ms, len(transcript_json))

        # 7. Webhook
        webhook_url = params.get("webhook_url") or job.webhook_url
        if webhook_url:
            from app.workers.webhook_tasks import deliver_webhook

            deliver_webhook.delay(
                job_id=job_id,
                webhook_url=webhook_url,
                event="job.completed",
            )

    except httpx.ConnectError as exc:
        logger.warning("whisper_connection_error", job_id=job_id, error=str(exc))
        _update_job_status(job_id, "queued", progress=0)
        raise self.retry(exc=exc, countdown=15 * (2 ** self.request.retries))

    except Exception as exc:
        error_trace = traceback.format_exc()
        logger.error("stt_task_failed", job_id=job_id, error=str(exc))

        if self.request.retries >= self.max_retries:
            _update_job_status(
                job_id, "dead_letter",
                error_message=str(exc), error_trace=error_trace,
                retry_count=self.request.retries,
            )
        else:
            _update_job_status(
                job_id, "failed",
                error_message=str(exc), error_trace=error_trace,
                retry_count=self.request.retries,
            )
            raise self.retry(exc=exc, countdown=15 * (2 ** self.request.retries))


@celery_app.task(
    name="workers.voice_tasks.synthesize_speech",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def synthesize_speech(self, job_id: str):
    """
    Text-to-speech synthesis via Kokoro FastAPI (OpenAI-compatible endpoint).

    POST text to Kokoro /v1/audio/speech → store audio file in MinIO.
    """
    logger.info("tts_task_started", job_id=job_id, attempt=self.request.retries + 1)
    start_time = time.monotonic()

    _update_job_status(job_id, "processing", progress=10)

    job = _get_job(job_id)
    if not job:
        logger.error("job_not_found", job_id=job_id)
        return

    params = job.input_params or {}

    try:
        from app.services.storage import get_storage

        storage = get_storage()

        # 1. Build TTS request (OpenAI-compatible format)
        tts_payload = {
            "model": "kokoro",
            "input": params.get("text", ""),
            "voice": params.get("voice", "af_bella"),
            "speed": params.get("speed", 1.0),
            "response_format": "mp3",
        }

        if not tts_payload["input"]:
            raise ValueError("No text provided for TTS synthesis")

        _update_job_status(job_id, "processing", progress=30)

        # 2. Call Kokoro API
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{settings.KOKORO_API_URL}/v1/audio/speech",
                json=tts_payload,
            )

        _update_job_status(job_id, "processing", progress=70)

        if response.status_code != 200:
            raise RuntimeError(
                f"Kokoro API returned {response.status_code}: {response.text[:500]}"
            )

        # 3. Upload audio to MinIO
        audio_data = response.content
        output_key = f"voice_tts/{job_id}/{uuid.uuid4()}.mp3"

        storage.upload_file(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=output_key,
            data=audio_data,
            content_type="audio/mpeg",
        )

        _update_job_status(job_id, "processing", progress=85)

        # 4. Generate presigned URL
        output_url = storage.generate_presigned_url(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=output_key,
            ttl_hours=settings.OUTPUT_URL_TTL_HOURS,
        )

        # 5. Mark completed
        compute_ms = int((time.monotonic() - start_time) * 1000)
        _update_job_status(
            job_id,
            "completed",
            progress=100,
            output_file_key=output_key,
            output_url=output_url,
        )

        logger.info(
            "tts_task_completed",
            job_id=job_id,
            compute_time_ms=compute_ms,
            output_size=len(audio_data),
        )

        _record_usage(job_id, "voice_tts", compute_ms, len(audio_data))

        # 6. Webhook
        webhook_url = params.get("webhook_url") or job.webhook_url
        if webhook_url:
            from app.workers.webhook_tasks import deliver_webhook

            deliver_webhook.delay(
                job_id=job_id,
                webhook_url=webhook_url,
                event="job.completed",
            )

    except httpx.ConnectError as exc:
        logger.warning("kokoro_connection_error", job_id=job_id, error=str(exc))
        _update_job_status(job_id, "queued", progress=0)
        raise self.retry(exc=exc, countdown=10 * (2 ** self.request.retries))

    except Exception as exc:
        error_trace = traceback.format_exc()
        logger.error("tts_task_failed", job_id=job_id, error=str(exc))

        if self.request.retries >= self.max_retries:
            _update_job_status(
                job_id, "dead_letter",
                error_message=str(exc), error_trace=error_trace,
                retry_count=self.request.retries,
            )
        else:
            _update_job_status(
                job_id, "failed",
                error_message=str(exc), error_trace=error_trace,
                retry_count=self.request.retries,
            )
            raise self.retry(exc=exc, countdown=10 * (2 ** self.request.retries))
