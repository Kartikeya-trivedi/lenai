"""
Inference endpoint — POST /v1/infer/{modality}
Accepts requests for image, voice_stt, voice_tts, and video.
Returns a job ID immediately; inference runs asynchronously.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_api_key
from app.models.api_key import ApiKey
from app.models.job import Modality
from app.schemas.inference import (
    ImageGenerationRequest,
    InferenceResponse,
    VideoRequest,
    VoiceSTTRequest,
    VoiceTTSRequest,
)
from app.services.inference import InferenceService
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Inference"])

VALID_MODALITIES = {m.value for m in Modality}


@router.post(
    "/infer/{modality}",
    response_model=InferenceResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an inference request",
    description="Submit an async inference job. Returns a job ID for polling.",
)
async def create_inference_job(
    modality: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
    # Image / TTS / Video params come as JSON body
    prompt: Optional[str] = Form(default=None),
    negative_prompt: Optional[str] = Form(default=None),
    width: Optional[int] = Form(default=512),
    height: Optional[int] = Form(default=512),
    steps: Optional[int] = Form(default=20),
    cfg_scale: Optional[float] = Form(default=7.0),
    text: Optional[str] = Form(default=None),
    voice: Optional[str] = Form(default="af_bella"),
    speed: Optional[float] = Form(default=1.0),
    webhook_url: Optional[str] = Form(default=None),
    # Audio file for STT
    file: Optional[UploadFile] = File(default=None),
):
    """
    Unified inference endpoint for all modalities.
    
    - **image**: text-to-image generation via Stable Diffusion
    - **voice_stt**: speech-to-text transcription via Whisper
    - **voice_tts**: text-to-speech synthesis via Kokoro
    - **video**: frame-based video generation via SD img2img
    """
    # Validate modality
    if modality not in VALID_MODALITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid modality '{modality}'. Must be one of: {VALID_MODALITIES}",
        )

    # Check scope
    if not api_key.has_scope(modality):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key does not have scope for '{modality}'",
        )

    # Build params dict based on modality
    params = _build_params(modality, locals())

    import os
    if os.getenv("SKIP_AUTH", "").lower() == "true":
        import uuid
        import asyncio
        from app.demo_state import FAKE_JOBS
        
        job_id = uuid.uuid4()
        FAKE_JOBS[str(job_id)] = {"status": "processing", "modality": modality}
        
        async def run_modal_demo(jid: str, mod: str, p: dict):
            try:
                import modal
                if mod == Modality.IMAGE.value:
                    f = modal.Function.from_name("lenai-platform", "generate_image_modal")
                    base64_img = await f.remote.aio(
                        prompt=p.get("prompt", "A beautiful sunset") or "A beautiful sunset",
                        negative_prompt=p.get("negative_prompt", ""),
                        width=int(p.get("width", 512) or 512),
                        height=int(p.get("height", 512) or 512),
                        steps=int(p.get("steps", 20) or 20)
                    )
                    job_data = FAKE_JOBS[jid] or {}
                    job_data["status"] = "completed"
                    job_data["output_url"] = f"data:image/png;base64,{base64_img}"
                    job_data["progress"] = 100
                    FAKE_JOBS[jid] = job_data
                else:
                    job_data = FAKE_JOBS[jid] or {}
                    job_data["status"] = "failed"
                    job_data["error_message"] = "Only image generation is supported in demo mode without DB."
                    FAKE_JOBS[jid] = job_data
            except Exception as e:
                job_data = FAKE_JOBS[jid] or {}
                job_data["status"] = "failed"
                job_data["error_message"] = str(e)
                FAKE_JOBS[jid] = job_data
                
        background_tasks.add_task(run_modal_demo, str(job_id), modality, params)
        
        return InferenceResponse(
            job_id=job_id,
            status="processing",
            poll_url=f"/v1/jobs/{job_id}",
            estimated_seconds=_estimate_time(modality),
            message=f"{modality} job queued in demo mode",
        )

    # Create and enqueue job
    service = InferenceService(db)
    job = await service.create_job(
        modality=modality,
        params=params,
        tenant_id=api_key.tenant_id,
        api_key_id=api_key.id,
        file=file,
    )

    return InferenceResponse(
        job_id=job.id,
        status=job.status,
        poll_url=f"/v1/jobs/{job.id}",
        estimated_seconds=_estimate_time(modality),
        message=f"{modality} job queued successfully",
    )


def _build_params(modality: str, local_vars: dict) -> dict:
    """Build modality-specific params dict from form fields."""
    if modality == Modality.IMAGE.value:
        return {
            "prompt": local_vars.get("prompt", ""),
            "negative_prompt": local_vars.get("negative_prompt"),
            "width": local_vars.get("width", 512),
            "height": local_vars.get("height", 512),
            "steps": local_vars.get("steps", 20),
            "cfg_scale": local_vars.get("cfg_scale", 7.0),
            "webhook_url": local_vars.get("webhook_url"),
        }
    elif modality == Modality.VOICE_STT.value:
        return {
            "language": local_vars.get("voice"),  # reuse voice field for language
            "webhook_url": local_vars.get("webhook_url"),
        }
    elif modality == Modality.VOICE_TTS.value:
        return {
            "text": local_vars.get("text", ""),
            "voice": local_vars.get("voice", "af_bella"),
            "speed": local_vars.get("speed", 1.0),
            "webhook_url": local_vars.get("webhook_url"),
        }
    elif modality == Modality.VIDEO.value:
        return {
            "prompt": local_vars.get("prompt", ""),
            "webhook_url": local_vars.get("webhook_url"),
        }
    return {}


def _estimate_time(modality: str) -> int:
    """Return estimated processing time in seconds."""
    estimates = {
        Modality.IMAGE.value: 60,
        Modality.VOICE_STT.value: 30,
        Modality.VOICE_TTS.value: 10,
        Modality.VIDEO.value: 120,
    }
    return estimates.get(modality, 60)
