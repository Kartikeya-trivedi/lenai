"""
Media file validation and processing utilities.
"""

from __future__ import annotations

import io
from typing import Optional, Tuple

from PIL import Image

# Allowed file types per modality
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3",
    "audio/mp4", "audio/m4a", "audio/flac", "audio/ogg",
    "audio/webm", "audio/x-flac",
}


def validate_image_file(
    data: bytes,
    content_type: str,
    max_size_mb: int = 100,
) -> Tuple[bool, Optional[str]]:
    """Validate an uploaded image file."""
    if content_type not in ALLOWED_IMAGE_TYPES:
        return False, f"Unsupported image type: {content_type}. Allowed: {ALLOWED_IMAGE_TYPES}"

    size_mb = len(data) / (1024 * 1024)
    if size_mb > max_size_mb:
        return False, f"File size {size_mb:.1f}MB exceeds {max_size_mb}MB limit"

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception as e:
        return False, f"Invalid image file: {e}"

    return True, None


def validate_audio_file(
    data: bytes,
    content_type: str,
    max_size_mb: int = 100,
) -> Tuple[bool, Optional[str]]:
    """Validate an uploaded audio file."""
    if content_type not in ALLOWED_AUDIO_TYPES:
        return False, f"Unsupported audio type: {content_type}. Allowed: {ALLOWED_AUDIO_TYPES}"

    size_mb = len(data) / (1024 * 1024)
    if size_mb > max_size_mb:
        return False, f"File size {size_mb:.1f}MB exceeds {max_size_mb}MB limit"

    return True, None


def resize_image(data: bytes, width: int, height: int) -> bytes:
    """Resize image to target dimensions (for model input preprocessing)."""
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
