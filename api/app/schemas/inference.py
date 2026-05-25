"""
Pydantic schemas for inference requests and responses per modality.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ImageGenerationRequest(BaseModel):
    """Text-to-image generation request."""

    prompt: str = Field(..., min_length=1, max_length=2000, description="Text prompt")
    negative_prompt: Optional[str] = Field(
        default=None, max_length=2000, description="Negative prompt"
    )
    width: int = Field(default=512, ge=128, le=1024, description="Image width")
    height: int = Field(default=512, ge=128, le=1024, description="Image height")
    steps: int = Field(default=20, ge=1, le=50, description="Inference steps")
    cfg_scale: float = Field(default=7.0, ge=1.0, le=30.0, description="CFG scale")
    seed: Optional[int] = Field(default=None, description="Random seed for reproducibility")
    webhook_url: Optional[str] = Field(
        default=None, description="Callback URL for job completion"
    )

    @field_validator("width", "height")
    @classmethod
    def must_be_multiple_of_8(cls, v: int) -> int:
        if v % 8 != 0:
            raise ValueError("Must be a multiple of 8")
        return v


class VoiceSTTRequest(BaseModel):
    """Speech-to-text request (file uploaded separately as multipart)."""

    language: Optional[str] = Field(
        default=None, description="Language code (e.g., 'en', 'es')"
    )
    webhook_url: Optional[str] = Field(
        default=None, description="Callback URL for job completion"
    )


class VoiceTTSRequest(BaseModel):
    """Text-to-speech request."""

    text: str = Field(
        ..., min_length=1, max_length=5000, description="Text to synthesize"
    )
    voice: str = Field(default="af_bella", description="Voice ID")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech speed")
    response_format: str = Field(default="mp3", description="Output format")
    webhook_url: Optional[str] = Field(
        default=None, description="Callback URL for job completion"
    )


class InferenceResponse(BaseModel):
    """Immediate response after submitting an inference request."""

    job_id: uuid.UUID = Field(..., description="Unique job identifier")
    status: str = Field(default="queued", description="Initial job status")
    poll_url: str = Field(..., description="URL to poll for job status")
    estimated_seconds: Optional[int] = Field(
        default=None, description="Estimated processing time"
    )
    message: str = Field(
        default="Job queued successfully",
        description="Human-readable status message",
    )
