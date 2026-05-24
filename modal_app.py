"""
LenAI — Cloud Deployment Script (Modal + Supabase)
===================================================
This script defines the serverless cloud architecture using Modal.
It deploys the FastAPI gateway and dynamically provisions GPU functions
for media inference, downloading weights into a volume during build time.
"""

import modal

# ---------------------------------------------------------------------------
# Modal App & Volume Configuration
# ---------------------------------------------------------------------------
app = modal.App("lenai-platform")

# A shared volume to cache model weights so we don't redownload them across containers
model_volume = modal.Volume.from_name("lenai-models", create_if_missing=True)
CACHE_DIR = "/models"

# The pre-existing volume containing Llama 3.1 8B, Gemma 27B, and the RAG embedding/reranker models
rag_models_volume = modal.Volume.from_name("ktgpt-rag-models")

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
    .pip_install("pip>=24.0") # Upgrade pip to handle new wheels
    .pip_install(
        "torch",
        "diffusers",
        "transformers",
        "accelerate",
        "openai-whisper",
        "ffmpeg-python"
    )
    .apt_install("ffmpeg")
    .run_function(download_sd_weights, volumes={CACHE_DIR: model_volume})
    .run_function(download_whisper_weights, volumes={CACHE_DIR: model_volume})
)

# Image for the vLLM OpenAI-compatible server
vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("vllm==0.5.4") # Pinned for stability
)

# Ignore patterns for local dir mounting (no file reading - runs inside container too)
ignore_patterns = [
    "__pycache__/", "*.pyc", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".venv/", "venv/", ".git", ".env", ".env.*",
]

# Image for the FastAPI API Gateway
api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("api/requirements.txt")
    .pip_install("aiofiles")  # Required by FastAPI StaticFiles
    # add_local_dir MUST come last in the build chain
    .add_local_dir("./api/app", remote_path="/root/app", ignore=ignore_patterns)
    .add_local_dir("./playground", remote_path="/root/playground")
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
# Serverless LLM / RAG Engine (vLLM)
# ---------------------------------------------------------------------------
@app.function(
    image=vllm_image,
    gpu="A10G", # 24GB VRAM (perfect for Llama 3.1 8B fp16)
    volumes={"/models": rag_models_volume},
    scaledown_window=300, # Keep the LLM warm for 5 minutes
)
@modal.concurrent(max_inputs=100)
@modal.web_server(8000, startup_timeout=300)
def vllm_server():
    """Starts the vLLM OpenAI-compatible server on port 8000."""
    import subprocess
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", "/models/llama-3.1-8b-instruct",
        "--port", "8000"
    ]
    subprocess.Popen(cmd)


# ---------------------------------------------------------------------------
# API Gateway
# ---------------------------------------------------------------------------
# We import the FastAPI app instance from our existing code
# Note: In a true cloud environment, we would modify `api/app/workers/image_tasks.py` 
# to call `generate_image_modal.remote(prompt)` instead of using Celery.

@app.function(
    image=api_image,
    # secrets=[modal.Secret.from_name("lenai-db-secret")], # Commented out so deployment passes without DB
    volumes={"/models": rag_models_volume} # Mount RAG embedding models
)
@modal.asgi_app()
def api_gateway():
    """Mounts the entire FastAPI application onto Modal."""
    import os
    # Dynamically inject the vLLM server URL and point to local RAG models
    os.environ["VLLM_API_URL"] = vllm_server.web_url
    os.environ["EMBEDDING_MODEL"] = "/models/multilingual-e5-large"
    os.environ["RERANKER_MODEL"] = "/models/ms-marco-MiniLM-L-6-v2"
    os.environ["SKIP_AUTH"] = "true"  # Bypass API key validation (no DB)
    
    from app.main import app as fastapi_app
    from fastapi.staticfiles import StaticFiles
    
    # Mount the frontend directory so Modal serves the Developer Playground!
    fastapi_app.mount("/playground", StaticFiles(directory="/root/playground", html=True), name="playground")
    
    return fastapi_app
