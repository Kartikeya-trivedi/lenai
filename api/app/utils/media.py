"""
Media file validation and processing utilities.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Allowed file types per modality
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3",
    "audio/mp4", "audio/m4a", "audio/flac", "audio/ogg",
    "audio/webm", "audio/x-flac",
}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/avi"}


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


def extract_video_frames(
    video_path: str,
    fps: int = 8,
    output_dir: str = "/tmp/frames",
) -> List[str]:
    """Extract frames from video using ffmpeg."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_pattern = str(Path(output_dir) / "frame_%05d.png")

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        output_pattern,
        "-y",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg_extract_failed", error=e.stderr.decode())
        raise RuntimeError(f"Frame extraction failed: {e.stderr.decode()}")

    frames = sorted(Path(output_dir).glob("frame_*.png"))
    return [str(f) for f in frames]


def assemble_video_frames(
    frame_dir: str,
    fps: int = 8,
    output_path: str = "/tmp/output.mp4",
) -> str:
    """Reassemble frames into video using ffmpeg."""
    input_pattern = str(Path(frame_dir) / "frame_%05d.png")

    cmd = [
        "ffmpeg",
        "-framerate", str(fps),
        "-i", input_pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        output_path,
        "-y",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg_assemble_failed", error=e.stderr.decode())
        raise RuntimeError(f"Video assembly failed: {e.stderr.decode()}")

    return output_path


def get_media_info(file_path: str) -> dict:
    """Get media file info (duration, dimensions, format) via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        file_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        import json
        return json.loads(result.stdout)
    except Exception as e:
        logger.warning("ffprobe_failed", file=file_path, error=str(e))
        return {}
