"""
Video inference Celery task — frame-based video style transfer.

Flow:
  1. Download source image/video from MinIO
  2. Extract frames with FFmpeg
  3. For each frame: call SD img2img API with style prompt
  4. Reassemble frames with FFmpeg
  5. Upload result, generate presigned URL
  6. Update progress per-frame for real-time polling
"""

from __future__ import annotations

import base64
import io
import os
import shutil
import tempfile
import time
import traceback
import uuid

import httpx

from app.workers.celery_app import celery_app
from app.workers.image_tasks import (
    _get_job,
    _record_usage,
    _update_job_status,
)
from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@celery_app.task(
    name="workers.video_tasks.process_video",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
    soft_time_limit=600,
    time_limit=720,
)
def process_video(self, job_id: str):
    """
    Frame-based video style transfer using Stable Diffusion img2img.

    This is an honest, functional approach that reuses the SD model:
    - Extract frames from source at configurable FPS
    - Apply SD img2img to each frame with style prompt
    - Reassemble styled frames into output video

    Limitations (documented in README):
    - Temporal coherence is not guaranteed between frames
    - Processing time scales linearly with frame count
    - Best for short clips (< 10 seconds)
    """
    logger.info("video_task_started", job_id=job_id, attempt=self.request.retries + 1)
    start_time = time.monotonic()

    _update_job_status(job_id, "processing", progress=5)

    job = _get_job(job_id)
    if not job:
        logger.error("job_not_found", job_id=job_id)
        return

    params = job.input_params or {}
    prompt = params.get("prompt", "")
    target_fps = params.get("fps", 8)
    max_frames = params.get("max_frames", 24)

    workdir = tempfile.mkdtemp(prefix="lenai_video_")

    try:
        from app.services.storage import get_storage
        from app.utils.media import extract_video_frames, assemble_video_frames

        storage = get_storage()

        # 1. Download source from MinIO
        if not job.input_file_key:
            raise ValueError("No input file provided for video processing")

        source_data = storage.download_file(
            bucket=settings.MINIO_BUCKET_INPUTS,
            key=job.input_file_key,
        )

        # Determine if source is image or video
        ext = job.input_file_key.rsplit(".", 1)[-1].lower() if "." in job.input_file_key else "mp4"
        source_path = os.path.join(workdir, f"source.{ext}")
        with open(source_path, "wb") as f:
            f.write(source_data)

        _update_job_status(job_id, "processing", progress=10)

        # 2. Extract frames
        frames_dir = os.path.join(workdir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        if ext in ("mp4", "avi", "mov", "webm", "mkv"):
            frame_paths = extract_video_frames(
                video_path=source_path,
                output_dir=frames_dir,
                fps=target_fps,
            )
        else:
            # Source is a single image — duplicate it for a short animation
            import shutil
            frame_paths = []
            for i in range(min(max_frames, 8)):
                frame_path = os.path.join(frames_dir, f"frame_{i:04d}.png")
                shutil.copy2(source_path, frame_path)
                frame_paths.append(frame_path)

        # Limit frames
        frame_paths = frame_paths[:max_frames]
        total_frames = len(frame_paths)
        logger.info("frames_extracted", job_id=job_id, total_frames=total_frames)

        _update_job_status(job_id, "processing", progress=20)

        # 3. Apply SD img2img to each frame
        styled_dir = os.path.join(workdir, "styled")
        os.makedirs(styled_dir, exist_ok=True)

        for i, frame_path in enumerate(frame_paths):
            # Read frame as base64
            with open(frame_path, "rb") as f:
                frame_b64 = base64.b64encode(f.read()).decode()

            # Call SD img2img
            img2img_payload = {
                "init_images": [frame_b64],
                "prompt": prompt,
                "negative_prompt": params.get("negative_prompt", ""),
                "steps": params.get("steps", 15),  # Fewer steps for speed
                "cfg_scale": params.get("cfg_scale", 7.0),
                "denoising_strength": params.get("denoising_strength", 0.5),
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "batch_size": 1,
                "seed": params.get("seed", -1),
            }

            try:
                with httpx.Client(timeout=300.0) as client:
                    resp = client.post(
                        f"{settings.SD_API_URL}/sdapi/v1/img2img",
                        json=img2img_payload,
                    )

                if resp.status_code == 200:
                    result = resp.json()
                    images = result.get("images", [])
                    if images:
                        styled_data = base64.b64decode(images[0])
                        styled_path = os.path.join(styled_dir, f"frame_{i:04d}.png")
                        with open(styled_path, "wb") as f:
                            f.write(styled_data)
                    else:
                        # Fallback: copy original frame
                        shutil.copy2(frame_path, os.path.join(styled_dir, f"frame_{i:04d}.png"))
                else:
                    logger.warning(
                        "frame_processing_failed",
                        job_id=job_id,
                        frame=i,
                        status=resp.status_code,
                    )
                    shutil.copy2(frame_path, os.path.join(styled_dir, f"frame_{i:04d}.png"))

            except Exception as frame_exc:
                logger.warning(
                    "frame_sd_error",
                    job_id=job_id,
                    frame=i,
                    error=str(frame_exc),
                )
                shutil.copy2(frame_path, os.path.join(styled_dir, f"frame_{i:04d}.png"))

            # Update progress (20% to 80% range for frame processing)
            progress = 20 + int((i + 1) / total_frames * 60)
            _update_job_status(job_id, "processing", progress=progress)

        # 4. Reassemble frames into video
        output_path = os.path.join(workdir, "output.mp4")
        assemble_video_frames(
            frames_dir=styled_dir,
            output_path=output_path,
            fps=target_fps,
        )

        _update_job_status(job_id, "processing", progress=90)

        # 5. Upload result to MinIO
        with open(output_path, "rb") as f:
            video_data = f.read()

        output_key = f"video/{job_id}/{uuid.uuid4()}.mp4"
        storage.upload_file(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=output_key,
            data=video_data,
            content_type="video/mp4",
        )

        # 6. Generate presigned URL
        output_url = storage.generate_presigned_url(
            bucket=settings.MINIO_BUCKET_OUTPUTS,
            key=output_key,
            ttl_hours=settings.OUTPUT_URL_TTL_HOURS,
        )

        # 7. Mark completed
        compute_ms = int((time.monotonic() - start_time) * 1000)
        _update_job_status(
            job_id,
            "completed",
            progress=100,
            output_file_key=output_key,
            output_url=output_url,
        )

        logger.info(
            "video_task_completed",
            job_id=job_id,
            total_frames=total_frames,
            compute_time_ms=compute_ms,
        )

        _record_usage(job_id, "video", compute_ms, len(video_data))

        # 8. Webhook
        webhook_url = params.get("webhook_url") or job.webhook_url
        if webhook_url:
            from app.workers.webhook_tasks import deliver_webhook
            deliver_webhook.delay(job_id=job_id, webhook_url=webhook_url, event="job.completed")

    except Exception as exc:
        error_trace = traceback.format_exc()
        logger.error("video_task_failed", job_id=job_id, error=str(exc))

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
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass
