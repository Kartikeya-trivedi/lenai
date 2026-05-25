"""
LenAI — Cloud Deployment Script (Modal + Supabase)
===================================================
This script defines the serverless cloud architecture using Modal.
It deploys the FastAPI gateway and dynamically provisions GPU functions
for image/LLM inference plus CPU voice workers, downloading weights into a
volume during build time.
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
def download_kokoro_models():
    import os
    import sys
    import urllib.request
    import subprocess
    
    print("Downloading Kokoro models to volume...")
    
    # 1. Main .pth file
    os.makedirs(f"{CACHE_DIR}/kokoro", exist_ok=True)
    model_path = f"{CACHE_DIR}/kokoro/kokoro-v1_0.pth"
    if not os.path.exists(model_path):
        urllib.request.urlretrieve("https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v1_0.pth", model_path)
    
    # 2. Voice profiles via huggingface_hub cache
    os.environ["HF_HOME"] = CACHE_DIR
    from huggingface_hub import hf_hub_download
    hf_hub_download(repo_id="hexgrad/Kokoro-82M", filename="voices/af_bella.pt")
    
    # 3. Spacy english pipeline (installed into volume)
    spacy_dir = f"{CACHE_DIR}/spacy_models"
    os.makedirs(spacy_dir, exist_ok=True)
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", 
        "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl", 
        "--target", spacy_dir
    ])
    print("Kokoro models downloaded.")

def download_sd_weights():
    from diffusers import DiffusionPipeline
    import torch
    print("Downloading FLUX.2 Klein 4B weights...")
    DiffusionPipeline.from_pretrained(
        "black-forest-labs/FLUX.2-klein-4B",
        torch_dtype=torch.bfloat16,
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

# Image for GPU image generation workers.
image_generation_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("pip>=24.0")
    .pip_install(
        "torch",
        "diffusers",
        "transformers",
        "accelerate",
        "sentencepiece",
        "protobuf",
    )
    .run_function(download_sd_weights, volumes={CACHE_DIR: model_volume})
)

# Image for CPU voice workers. Whisper tiny and Kokoro do not need GPU here.
voice_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("pip>=24.0")
    .pip_install(
        "torch",
        "openai-whisper",
        "ffmpeg-python",
        "kokoro>=0.3.4",
        "soundfile",
        "fastapi[standard]",
        "huggingface_hub",
        "numpy",
    )
    .apt_install("ffmpeg", "espeak-ng")
    .run_function(download_whisper_weights, volumes={CACHE_DIR: model_volume})
    .run_function(download_kokoro_models, volumes={CACHE_DIR: model_volume})
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
    .add_local_file("./api/model_registry.yaml", remote_path="/root/model_registry.yaml")
    .add_local_dir("./playground", remote_path="/root/playground")
)

# ---------------------------------------------------------------------------
# Serverless Inference Functions
# ---------------------------------------------------------------------------
@app.function(
    image=image_generation_image,
    gpu="A10G",
    volumes={CACHE_DIR: model_volume},
    scaledown_window=120,
    min_containers=1,
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
    image=voice_image,
    volumes={CACHE_DIR: model_volume},
    scaledown_window=60,
)
def transcribe_audio_modal(audio_bytes: bytes, language: str = None):
    return _transcribe_audio_bytes(audio_bytes, language=language)


def _transcribe_audio_bytes(audio_bytes: bytes, language: str = None):
    import whisper
    import tempfile
    import os
    model = whisper.load_model("tiny", download_root=CACHE_DIR)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    try:
        result = model.transcribe(tmp_path, language=language)
        return result
    finally:
        os.remove(tmp_path)

@app.function(
    image=voice_image,
    volumes={CACHE_DIR: model_volume},
    scaledown_window=60,
)
@modal.fastapi_endpoint(method="POST")
def transcribe_audio_http(payload: dict):
    import base64

    audio_bytes = base64.b64decode(payload["audio_base64"])
    return _transcribe_audio_bytes(audio_bytes, language=payload.get("language"))

@app.function(
    image=voice_image,
    volumes={CACHE_DIR: model_volume},
    scaledown_window=60,
)
def synthesize_speech_modal(text: str, voice: str = "af_bella", speed: float = 1.0):
    return _synthesize_speech_bytes(text=text, voice=voice, speed=speed)


def _synthesize_speech_bytes(text: str, voice: str = "af_bella", speed: float = 1.0):
    import os
    import sys
    import subprocess
    import tempfile
    
    # Load spacy models from the persistent volume
    sys.path.insert(0, f"{CACHE_DIR}/spacy_models")
    os.environ["HF_HOME"] = CACHE_DIR
    
    import soundfile as sf
    import numpy as np
    from kokoro import KPipeline
    
    pipeline = KPipeline(lang_code='a')
    generator = pipeline(text, voice=voice, speed=speed)
    
    audio_chunks = []
    for _, _, audio in generator:
        if audio is not None:
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            else:
                audio = np.asarray(audio)
            audio_chunks.append(audio.astype("float32"))

    if not audio_chunks:
        raise ValueError("Kokoro produced no audio")

    audio_data = np.concatenate(audio_chunks)

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "speech.wav")
        mp3_path = os.path.join(tmpdir, "speech.mp3")
        sf.write(wav_path, audio_data, 24000, format="WAV")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                wav_path,
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                mp3_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(mp3_path, "rb") as f:
            return f.read()

@app.function(
    image=voice_image,
    volumes={CACHE_DIR: model_volume},
    scaledown_window=60,
)
@modal.fastapi_endpoint(method="POST")
def synthesize_speech_http(payload: dict):
    import base64

    audio_bytes = _synthesize_speech_bytes(
        text=payload.get("text", ""),
        voice=payload.get("voice", "af_bella"),
        speed=float(payload.get("speed", 1.0)),
    )
    return {"audio_base64": base64.b64encode(audio_bytes).decode("ascii")}

# ---------------------------------------------------------------------------
# Serverless LLM / RAG Engine (vLLM)
# ---------------------------------------------------------------------------
@app.function(
    image=vllm_image,
    gpu="A10G",
    volumes={"/models": rag_models_volume},
    scaledown_window=300,
    min_containers=1,
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
def _install_modal_worker_handles():
    import sys
    import types

    handles = types.ModuleType("app.modal_handles")
    handles.MODAL_FUNCTIONS = {
        "generate_image_modal": generate_image_modal,
        "transcribe_audio_modal": transcribe_audio_modal,
        "synthesize_speech_modal": synthesize_speech_modal,
    }
    sys.modules["app.modal_handles"] = handles


def _get_modal_web_url(function):
    web_url = getattr(function, "web_url", None)
    if hasattr(web_url, "url"):
        return web_url.url
    get_web_url = getattr(function, "get_web_url", None)
    if callable(get_web_url):
        return get_web_url()
    return str(web_url)


def _install_modal_worker_urls():
    import os

    os.environ["MODAL_STT_URL"] = _get_modal_web_url(transcribe_audio_http)
    os.environ["MODAL_TTS_URL"] = _get_modal_web_url(synthesize_speech_http)


def _install_modal_enqueue_patch():
    from app.models.job import Modality
    from app.services.inference import InferenceService

    def _enqueue_task_modal(self, job):
        task_map = {
            Modality.IMAGE.value: "workers.image_tasks.generate_image",
            Modality.VOICE_STT.value: "workers.voice_tasks.transcribe_audio",
            Modality.VOICE_TTS.value: "workers.voice_tasks.synthesize_speech",
        }

        task_name = task_map.get(job.modality)
        if task_name is None:
            raise ValueError(f"No task registered for modality: {job.modality}")

        execute_celery_task_modal.spawn(task_name, str(job.id))
        return str(job.id)

    InferenceService._enqueue_task = _enqueue_task_modal


@app.function(
    image=api_image,
    secrets=[
        modal.Secret.from_name("lenai-db-secret"),
        modal.Secret.from_name("redis-secret"),
        modal.Secret.from_name("lenai-storage-secret"),
    ],
    volumes={"/models": rag_models_volume}
)
@modal.asgi_app()
def api_gateway():
    import os
    os.environ["RUNNING_IN_MODAL"] = "true"
    
    # 1. Inject internal vLLM URL
    os.environ["VLLM_API_URL"] = vllm_server.web_url.url if hasattr(vllm_server.web_url, 'url') else getattr(vllm_server, "get_web_url", lambda: vllm_server.web_url)()
    
    # 2. Configure RAG Engine to use downloaded weights in the volume
    os.environ["EMBEDDING_MODEL"] = "intfloat/multilingual-e5-large"
    os.environ["RERANKER_MODEL"] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = CACHE_DIR
    os.environ["HF_HOME"] = CACHE_DIR
    
    # 3. Security
    os.environ["CORS_ORIGINS"] = '["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "https://lenai-gamma.vercel.app", "https://lenai-gamma.vercel.app/"]'
    
    _install_modal_worker_handles()
    _install_modal_worker_urls()
    _install_modal_enqueue_patch()

    from app.main import app as fastapi_app
    from fastapi.staticfiles import StaticFiles
    
    fastapi_app.mount("/playground", StaticFiles(directory="/root/playground", html=True), name="playground")
    
    return fastapi_app


# ---------------------------------------------------------------------------
# Serverless Celery Task Execution
# ---------------------------------------------------------------------------
@app.function(
    secrets=[
        modal.Secret.from_name("lenai-db-secret"),
        modal.Secret.from_name("lenai-storage-secret"),
    ],
    image=api_image,
    timeout=600,
)
def execute_celery_task_modal(task_name: str, job_id: str):
    """
    Execute a Celery task synchronously in this Modal container.
    This replaces the need for a long-running Celery worker daemon.
    """
    import os
    os.environ["RUNNING_IN_MODAL"] = "true"
    _install_modal_worker_handles()
    _install_modal_worker_urls()
    
    from app.workers.celery_app import celery_app
    # Ensure tasks are registered
    import app.workers.image_tasks
    import app.workers.voice_tasks
    
    task = celery_app.tasks.get(task_name)
    if not task:
        raise ValueError(f"Task {task_name} not found")
        
    print(f"Executing task {task_name} for job {job_id} on Modal")
    task.apply(args=[job_id])

@app.function(
    secrets=[
        modal.Secret.from_name("lenai-db-secret"),
        modal.Secret.from_name("lenai-storage-secret"),
    ],
    image=api_image,
    timeout=600,
    schedule=modal.Cron("0 * * * *")
)
def cleanup_outputs_cron_modal():
    """
    Scheduled cron job to run the TTL cleanup task directly on Modal.
    """
    import os
    os.environ["RUNNING_IN_MODAL"] = "true"
    
    from app.workers.celery_app import celery_app
    import app.workers.cleanup_tasks
    
    task = celery_app.tasks.get("workers.cleanup_tasks.cleanup_expired_outputs")
    if task:
        print("Executing scheduled TTL cleanup on Modal...")
        task.apply()
