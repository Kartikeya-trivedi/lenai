"""
Inference orchestration — validates input, creates job, enqueues task.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.middleware.error_handler import ModelUnavailableError
from app.models.job import Job, JobStatus, Modality
from app.services.model_registry import get_model_registry
from app.services.storage import get_storage
from app.utils.logging import get_logger
from app.utils.media import validate_audio_file, validate_image_file

logger = get_logger(__name__)
settings = get_settings()


class InferenceService:
    """Orchestrates inference job creation, validation, and queuing."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.registry = get_model_registry()
        self.storage = get_storage()

    async def create_job(
        self,
        modality: str,
        params: dict,
        tenant_id: uuid.UUID,
        api_key_id: uuid.UUID,
        file: Optional[UploadFile] = None,
    ) -> Job:
        """
        Validate input, create DB record, upload file if present, enqueue task.
        Returns the created Job.
        """
        # 1. Check model availability
        model_config = self.registry.get_model_config(modality)
        if model_config is None:
            raise ModelUnavailableError(modality, "No model registered for this modality")

        # 2. Validate & preprocess input
        input_file_key = None
        if file is not None:
            input_file_key = await self._handle_file_upload(modality, file)

        # 3. Create job record in DB
        job = Job(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            modality=modality,
            status=JobStatus.PENDING.value,
            input_params=params,
            input_file_key=input_file_key,
            webhook_url=params.get("webhook_url"),
            progress=0,
        )
        self.db.add(job)
        await self.db.flush()

        # 4. Enqueue Celery task
        task_id = self._enqueue_task(job)
        job.status = JobStatus.QUEUED.value

        logger.info(
            "job_created",
            job_id=str(job.id),
            modality=modality,
            task_id=task_id,
        )

        return job

    async def _handle_file_upload(
        self,
        modality: str,
        file: UploadFile,
    ) -> str:
        """Validate and upload file to MinIO, return the object key."""
        data = await file.read()
        content_type = file.content_type or "application/octet-stream"

        # Validate based on modality
        if modality == Modality.VOICE_STT.value:
            valid, error = validate_audio_file(data, content_type, settings.MAX_UPLOAD_SIZE_MB)
        elif modality == Modality.IMAGE.value:
            valid, error = validate_image_file(data, content_type, settings.MAX_UPLOAD_SIZE_MB)
        else:
            valid, error = True, None

        if not valid:
            raise ValueError(error)

        # Upload to MinIO
        key = f"{modality}/{uuid.uuid4()}/{file.filename}"
        self.storage.upload_file(
            bucket=settings.MINIO_BUCKET_INPUTS,
            key=key,
            data=data,
            content_type=content_type,
        )

        return key

    def _enqueue_task(self, job: Job) -> str:
        """Enqueue the appropriate Celery task for this job."""
        from app.workers.celery_app import celery_app

        task_map = {
            Modality.IMAGE.value: "workers.image_tasks.generate_image",
            Modality.VOICE_STT.value: "workers.voice_tasks.transcribe_audio",
            Modality.VOICE_TTS.value: "workers.voice_tasks.synthesize_speech",
            Modality.VIDEO.value: "workers.video_tasks.process_video",
        }

        task_name = task_map.get(job.modality)
        if task_name is None:
            raise ValueError(f"No task registered for modality: {job.modality}")

        result = celery_app.send_task(
            task_name,
            args=[str(job.id)],
            queue=job.modality.split("_")[0],  # image, voice, video
        )

        return result.id
