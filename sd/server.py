"""
LenAI — Lightweight Stable Diffusion API Server
================================================
A minimal FastAPI wrapper around HuggingFace diffusers for txt2img and img2img.
Compatible with the AUTOMATIC1111 /sdapi/v1/ endpoint format.

Designed to be functional on CPU (slow) and GPU (fast with override).
"""

import base64
import io
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import torch
from diffusers import StableDiffusionPipeline, StableDiffusionImg2ImgPipeline
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_ID = os.getenv("SD_MODEL_ID", "runwayml/stable-diffusion-v1-5")
CACHE_DIR = os.getenv("SD_MODEL_CACHE", "/models")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16 if DEVICE == "cuda" else torch.float32

logger = logging.getLogger("sd-server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------------------------------------------------------------
# Global pipeline holders
# ---------------------------------------------------------------------------
txt2img_pipe: Optional[StableDiffusionPipeline] = None
img2img_pipe: Optional[StableDiffusionImg2ImgPipeline] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model weights on startup, release on shutdown."""
    global txt2img_pipe, img2img_pipe

    logger.info("Loading Stable Diffusion model: %s (device=%s, dtype=%s)", MODEL_ID, DEVICE, DTYPE)
    txt2img_pipe = StableDiffusionPipeline.from_pretrained(
        MODEL_ID,
        torch_dtype=DTYPE,
        cache_dir=CACHE_DIR,
        safety_checker=None,
        requires_safety_checker=False,
    ).to(DEVICE)

    # Enable memory-efficient attention if available
    if DEVICE == "cuda":
        try:
            txt2img_pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            logger.info("xformers not available, using default attention")

    # Reuse components for img2img to save memory
    img2img_pipe = StableDiffusionImg2ImgPipeline(
        vae=txt2img_pipe.vae,
        text_encoder=txt2img_pipe.text_encoder,
        tokenizer=txt2img_pipe.tokenizer,
        unet=txt2img_pipe.unet,
        scheduler=txt2img_pipe.scheduler,
        safety_checker=None,
        feature_extractor=None,
        requires_safety_checker=False,
    ).to(DEVICE)

    logger.info("✅ Stable Diffusion model loaded and ready")
    yield

    # Cleanup
    del txt2img_pipe, img2img_pipe
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    logger.info("Model unloaded")


app = FastAPI(title="LenAI SD Server", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Schemas (AUTOMATIC1111-compatible subset)
# ---------------------------------------------------------------------------
class Txt2ImgRequest(BaseModel):
    prompt: str = Field(..., description="Text prompt for image generation")
    negative_prompt: str = Field(default="", description="Negative prompt")
    width: int = Field(default=512, ge=64, le=1024)
    height: int = Field(default=512, ge=64, le=1024)
    steps: int = Field(default=20, ge=1, le=100, alias="num_inference_steps")
    cfg_scale: float = Field(default=7.5, ge=1.0, le=30.0, alias="guidance_scale")
    seed: int = Field(default=-1, description="Random seed (-1 for random)")
    batch_size: int = Field(default=1, ge=1, le=4)

    class Config:
        populate_by_name = True


class Img2ImgRequest(BaseModel):
    prompt: str = Field(..., description="Text prompt")
    negative_prompt: str = Field(default="")
    init_images: list[str] = Field(..., description="List of base64-encoded input images")
    width: int = Field(default=512, ge=64, le=1024)
    height: int = Field(default=512, ge=64, le=1024)
    steps: int = Field(default=20, ge=1, le=100, alias="num_inference_steps")
    cfg_scale: float = Field(default=7.5, ge=1.0, le=30.0, alias="guidance_scale")
    denoising_strength: float = Field(default=0.75, ge=0.0, le=1.0)
    seed: int = Field(default=-1)

    class Config:
        populate_by_name = True


class GenerationResponse(BaseModel):
    images: list[str] = Field(description="List of base64-encoded PNG images")
    parameters: dict = Field(default_factory=dict)
    info: str = Field(default="")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_generator(seed: int):
    """Create a torch generator with the given seed."""
    if seed == -1:
        return None
    gen = torch.Generator(device=DEVICE)
    gen.manual_seed(seed)
    return gen


def _pil_to_base64(img: Image.Image) -> str:
    """Convert a PIL Image to a base64-encoded PNG string."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _base64_to_pil(b64: str) -> Image.Image:
    """Decode a base64 string to a PIL Image."""
    # Strip optional data URI prefix
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    img_bytes = base64.b64decode(b64)
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/sdapi/v1/options")
async def get_options():
    """Health check / options endpoint (AUTOMATIC1111-compatible)."""
    return {
        "sd_model_checkpoint": MODEL_ID,
        "sd_backend": "diffusers",
        "device": DEVICE,
        "dtype": str(DTYPE),
    }


@app.post("/sdapi/v1/txt2img", response_model=GenerationResponse)
async def txt2img(req: Txt2ImgRequest):
    """Generate images from text prompt."""
    if txt2img_pipe is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    logger.info("txt2img: prompt=%r, %dx%d, steps=%d", req.prompt[:80], req.width, req.height, req.steps)

    generator = _get_generator(req.seed)

    try:
        result = txt2img_pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or None,
            width=req.width,
            height=req.height,
            num_inference_steps=req.steps,
            guidance_scale=req.cfg_scale,
            generator=generator,
            num_images_per_prompt=req.batch_size,
        )
    except Exception as e:
        logger.error("txt2img failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    images_b64 = [_pil_to_base64(img) for img in result.images]

    return GenerationResponse(
        images=images_b64,
        parameters={
            "prompt": req.prompt,
            "negative_prompt": req.negative_prompt,
            "width": req.width,
            "height": req.height,
            "steps": req.steps,
            "cfg_scale": req.cfg_scale,
            "seed": req.seed,
        },
    )


@app.post("/sdapi/v1/img2img", response_model=GenerationResponse)
async def img2img(req: Img2ImgRequest):
    """Generate images from image + text prompt."""
    if img2img_pipe is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not req.init_images:
        raise HTTPException(status_code=400, detail="init_images is required")

    logger.info("img2img: prompt=%r, strength=%.2f, steps=%d", req.prompt[:80], req.denoising_strength, req.steps)

    try:
        init_image = _base64_to_pil(req.init_images[0]).resize((req.width, req.height))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid init_image: {e}")

    generator = _get_generator(req.seed)

    try:
        result = img2img_pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or None,
            image=init_image,
            num_inference_steps=req.steps,
            guidance_scale=req.cfg_scale,
            strength=req.denoising_strength,
            generator=generator,
        )
    except Exception as e:
        logger.error("img2img failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    images_b64 = [_pil_to_base64(img) for img in result.images]

    return GenerationResponse(
        images=images_b64,
        parameters={
            "prompt": req.prompt,
            "denoising_strength": req.denoising_strength,
            "steps": req.steps,
            "cfg_scale": req.cfg_scale,
            "seed": req.seed,
        },
    )


@app.get("/health")
async def health():
    """Simple health check."""
    return {"status": "ok", "model_loaded": txt2img_pipe is not None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
