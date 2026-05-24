"""
LenAI — Cloud Deployment Script (Modal + Supabase)
===================================================
This script defines the serverless cloud architecture using Modal.
It deploys the FastAPI gateway and dynamically provisions GPU functions
for media inference, downloading weights into a volume during build time.
"""

import modal
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Modal App & Volume Configuration
# ---------------------------------------------------------------------------
app = modal.App("lenai-platform")

# A shared volume to cache model weights so we don't redownload them across containers
model_volume = modal.Volume.from_name("lenai-models", create_if_missing=True)
CACHE_DIR = "/models"

# ---------------------------------------------------------------------------
# Container Image Definitions
# ---------------------------------------------------------------------------
def download_sd_weights():
    """Downloads Stable Diffusion weights into the image cache at build time."""
    from diffusers import StableDiffusionPipeline
    import torch
    
    print("Downloading Stable Diffusion weights (v1-5)...")
    StableDiffusionPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float16,
        cache_dir=CACHE_DIR,
        safety_checker=None,
        requires_safety_checker=False,
    )
    print("Download complete.")

def download_whisper_weights():
    """Downloads Whisper weights into the image cache at build time."""
    import whisper
    print("Downloading Whisper tiny weights...")
    whisper.load_model("tiny", download_root=CACHE_DIR)
    print("Download complete.")

# Image for the GPU Inference workers
inference_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.1.2",
        "diffusers==0.25.0",
        "transformers==4.36.2",
        "accelerate==0.25.0",
        "openai-whisper==20231117",
        "ffmpeg-python==0.2.0"
    )
    .apt_install("ffmpeg")
    .run_function(download_sd_weights, volumes={CACHE_DIR: model_volume})
    .run_function(download_whisper_weights, volumes={CACHE_DIR: model_volume})
)

# Read ignore patterns
with open(".modalignore", "r") as f:
    ignore_patterns = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Image for the FastAPI API Gateway
api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("api/requirements.txt")
    .add_local_dir(
        "./api/app", 
        remote_path="/root/app", 
        ignore=ignore_patterns
    )
    .add_local_dir(
        "./playground", 
        remote_path="/root/playground",
        ignore=ignore_patterns
    )
)

# ---------------------------------------------------------------------------
# Serverless GPU Inference Functions
# ---------------------------------------------------------------------------
@app.function(
    image=inference_image,
    gpu="T4",
    volumes={CACHE_DIR: model_volume},
    scaledown_window=120, # Keep container warm for 2 mins after a request
)
def generate_image_modal(prompt: str, negative_prompt: str = "", width: int = 512, height: int = 512, steps: int = 20):
    """Generates an image using Stable Diffusion on a Serverless T4 GPU."""
    from diffusers import StableDiffusionPipeline
    import torch
    import io
    import base64
    
    # Load model (very fast because it's cached in the volume)
    pipe = StableDiffusionPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float16,
        cache_dir=CACHE_DIR,
        safety_checker=None,
        requires_safety_checker=False,
    ).to("cuda")
    
    pipe.enable_xformers_memory_efficient_attention()
    
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        num_inference_steps=steps,
    )
    
    image = result.images[0]
    
    # Convert to base64
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# API Gateway
# ---------------------------------------------------------------------------
# We import the FastAPI app instance from our existing code
# Note: In a true cloud environment, we would modify `api/app/workers/image_tasks.py` 
# to call `generate_image_modal.remote(prompt)` instead of using Celery.

@app.function(
    image=api_image,
    secrets=[modal.Secret.from_name("lenai-db-secret")], # Connects to Supabase
)
@modal.asgi_app()
def api_gateway():
    """Mounts the entire FastAPI application onto Modal."""
    from app.main import app as fastapi_app
    from fastapi.staticfiles import StaticFiles
    
    # Mount the frontend directory so Modal serves the Developer Playground!
    fastapi_app.mount("/playground", StaticFiles(directory="/root/playground", html=True), name="playground")
    
    return fastapi_app
