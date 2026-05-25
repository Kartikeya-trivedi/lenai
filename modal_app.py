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
    from diffusers import DiffusionPipeline, AutoPipelineForImage2Image
    import torch
    print("Downloading FLUX.2 Klein 4B weights...")
    DiffusionPipeline.from_pretrained(
        "black-forest-labs/FLUX.2-klein-4B",
        torch_dtype=torch.bfloat16,
        cache_dir=CACHE_DIR,
    )
    print("Downloading SD 1.5 weights (for Video Img2Img)...")
    AutoPipelineForImage2Image.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float16,
        cache_dir=CACHE_DIR,
    )
    print("Download complete.")

def download_whisper_weights():
    import whisper
    print("Downloading Whisper tiny weights...")
    whisper.load_model("tiny", download_root=CACHE_DIR)
    print("Download complete.")

def download_rag_models():
    import os
    # Download sentence transformers
    from transformers import AutoModel, AutoTokenizer, AutoModelForSequenceClassification
    print("Downloading RAG Embedding Models...")
    AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large", cache_dir=CACHE_DIR)
    AutoModel.from_pretrained("intfloat/multilingual-e5-large", cache_dir=CACHE_DIR)
    AutoTokenizer.from_pretrained("cross-encoder/ms-marco-MiniLM-L-6-v2", cache_dir=CACHE_DIR)
    AutoModelForSequenceClassification.from_pretrained("cross-encoder/ms-marco-MiniLM-L-6-v2", cache_dir=CACHE_DIR)
    print("RAG models downloaded.")

# Image for the GPU Inference workers
inference_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("pip>=24.0")
    .pip_install(
        "torch",
        "diffusers",
        "transformers",
        "accelerate",
        "sentencepiece",
        "protobuf",
        "openai-whisper",
        "ffmpeg-python",
        "kokoro>=0.3.4",
        "soundfile"
    )
    .apt_install("ffmpeg")
    .run_function(download_sd_weights, volumes={CACHE_DIR: model_volume})
    .run_function(download_whisper_weights, volumes={CACHE_DIR: model_volume})
)

# Image for the vLLM OpenAI-compatible server
vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("vllm")
)

# Image for the FastAPI API Gateway
ignore_patterns = [
    "__pycache__/", "*.pyc", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".venv/", "venv/", ".git", ".env", ".env.*",
]

api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("api/requirements.txt")
    .pip_install("aiofiles")
    .run_function(download_rag_models, volumes={CACHE_DIR: rag_models_volume})
    .add_local_dir("./api/app", remote_path="/root/app", ignore=ignore_patterns)
    .add_local_dir("./playground", remote_path="/root/playground")
)

# ---------------------------------------------------------------------------
# Serverless GPU Inference Functions
# ---------------------------------------------------------------------------
@app.function(
    image=inference_image,
    gpu="A10G",
    volumes={CACHE_DIR: model_volume},
    scaledown_window=120,
)
def generate_image_modal(prompt: str, negative_prompt: str = "", width: int = 512, height: int = 512, steps: int = 20):
    from diffusers import DiffusionPipeline
    import torch
    import io
    import base64
    
    pipe = DiffusionPipeline.from_pretrained(
        "black-forest-labs/FLUX.2-klein-4B",
        torch_dtype=torch.bfloat16,
        cache_dir=CACHE_DIR,
    ).to("cuda")
    
    result = pipe(
        prompt=prompt,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=3.5,
    )
    
    buf = io.BytesIO()
    result.images[0].save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

@app.function(
    image=inference_image,
    gpu="A10G",
    volumes={CACHE_DIR: model_volume},
    scaledown_window=60,
)
def transcribe_audio_modal(audio_bytes: bytes, language: str = None):
    import whisper
    import tempfile
    import os
    model = whisper.load_model("tiny", download_root=CACHE_DIR).to("cuda")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    try:
        result = model.transcribe(tmp_path, language=language)
        return result
    finally:
        os.remove(tmp_path)

@app.function(
    image=inference_image,
    gpu="A10G",
    volumes={CACHE_DIR: model_volume},
    scaledown_window=60,
)
def synthesize_speech_modal(text: str, voice: str = "af_bella", speed: float = 1.0):
    import urllib.request
    import os
    import soundfile as sf
    import io
    from kokoro import KPipeline
    
    # Download Kokoro weights on the fly if missing
    os.makedirs(f"{CACHE_DIR}/kokoro", exist_ok=True)
    model_path = f"{CACHE_DIR}/kokoro/kokoro-v1_0.pth"
    if not os.path.exists(model_path):
        urllib.request.urlretrieve("https://github.com/hexgrad/kokoro/releases/download/v1.0/kokoro-v1_0.pth", model_path)
    
    pipeline = KPipeline(lang_code='a')
    generator = pipeline(text, voice=voice, speed=speed)
    
    audio_chunks = []
    for _, _, audio in generator:
        if audio is not None:
            audio_chunks.extend(audio.tolist() if hasattr(audio, 'tolist') else audio)
            
    buf = io.BytesIO()
    sf.write(buf, audio_chunks, 24000, format='WAV')
    return buf.getvalue()

@app.function(
    image=inference_image,
    gpu="A10G",
    volumes={CACHE_DIR: model_volume},
    scaledown_window=120,
    timeout=600,
)
def process_video_modal(
    source_data: bytes, source_ext: str, prompt: str, negative_prompt: str = "",
    fps: int = 8, max_frames: int = 24, steps: int = 15, cfg_scale: float = 7.0,
    denoising_strength: float = 0.5, width: int = 512, height: int = 512, seed: int = -1
):
    import tempfile
    import os
    import subprocess
    import shutil
    import torch
    from PIL import Image
    from diffusers import AutoPipelineForImage2Image
    
    workdir = tempfile.mkdtemp()
    try:
        source_path = os.path.join(workdir, f"source.{source_ext}")
        with open(source_path, "wb") as f:
            f.write(source_data)
        
        frames_dir = os.path.join(workdir, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        
        if source_ext in ("mp4", "avi", "mov", "webm", "mkv"):
            cmd = ["ffmpeg", "-i", source_path, "-vf", f"fps={fps}", os.path.join(frames_dir, "frame_%04d.png")]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            frame_files = sorted(os.listdir(frames_dir))
        else:
            frame_files = []
            for i in range(min(max_frames, 8)):
                name = f"frame_{i:04d}.png"
                shutil.copy2(source_path, os.path.join(frames_dir, name))
                frame_files.append(name)
        
        frame_files = frame_files[:max_frames]
        
        pipe = AutoPipelineForImage2Image.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            torch_dtype=torch.float16,
            cache_dir=CACHE_DIR,
        ).to("cuda")
        
        styled_dir = os.path.join(workdir, "styled")
        os.makedirs(styled_dir, exist_ok=True)
        generator = torch.Generator("cuda").manual_seed(seed) if seed != -1 else None
        
        for name in frame_files:
            in_path = os.path.join(frames_dir, name)
            out_path = os.path.join(styled_dir, name)
            init_img = Image.open(in_path).convert("RGB").resize((width, height))
            result = pipe(
                prompt=prompt,
                image=init_img,
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                guidance_scale=cfg_scale,
                strength=denoising_strength,
                generator=generator
            )
            result.images[0].save(out_path)
            
        output_path = os.path.join(workdir, "output.mp4")
        cmd = ["ffmpeg", "-framerate", str(fps), "-i", os.path.join(styled_dir, "frame_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        with open(output_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

# ---------------------------------------------------------------------------
# Serverless LLM / RAG Engine (vLLM)
# ---------------------------------------------------------------------------
@app.function(
    image=vllm_image,
    gpu="A10G",
    volumes={"/models": rag_models_volume},
    scaledown_window=300,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(8000, startup_timeout=900)
def vllm_server():
    import subprocess
    import os
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", "/models/llama-3.1-8b-instruct",
        "--served-model-name", "meta-llama/Llama-3.1-8B-Instruct",
        "--max-model-len", "8192",
        "--port", "8000"
    ]
    env = os.environ.copy()
    env["VLLM_USE_FLASHINFER_SAMPLER"] = "0"
    subprocess.Popen(cmd, env=env)


# ---------------------------------------------------------------------------
# API Gateway
# ---------------------------------------------------------------------------
@app.function(
    image=api_image,
    secrets=[
        modal.Secret.from_name("lenai-db-secret"),
        modal.Secret.from_name("lenai-redis-secret", require=False),
        modal.Secret.from_name("lenai-storage-secret", require=False),
    ],
    volumes={"/models": rag_models_volume}
)
@modal.asgi_app()
def api_gateway():
    import os
    
    # 1. Inject internal vLLM URL
    os.environ["VLLM_API_URL"] = vllm_server.web_url.url if hasattr(vllm_server.web_url, 'url') else getattr(vllm_server, "get_web_url", lambda: vllm_server.web_url)()
    
    # 2. Configure RAG Engine to use downloaded weights in the volume
    os.environ["EMBEDDING_MODEL"] = "intfloat/multilingual-e5-large"
    os.environ["RERANKER_MODEL"] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = CACHE_DIR
    os.environ["HF_HOME"] = CACHE_DIR
    
    # 3. Security
    os.environ["CORS_ORIGINS"] = '["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]'
    
    from app.main import app as fastapi_app
    from fastapi.staticfiles import StaticFiles
    
    fastapi_app.mount("/playground", StaticFiles(directory="/root/playground", html=True), name="playground")
    
    return fastapi_app
