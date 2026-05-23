#!/usr/bin/env bash
# ============================================================
# LenAI — Model Weight Pre-Download Script
# ============================================================
# Downloads model weights before first `docker compose up` so
# container startup is faster. Run from the project root:
#
#   bash models/download.sh
#
# Weights are saved to ./models/weights/ which is mounted
# into containers via the sd_models volume.
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEIGHTS_DIR="${SCRIPT_DIR}/weights"

echo "📦 LenAI Model Pre-Download"
echo "   Target directory: ${WEIGHTS_DIR}"
echo ""

mkdir -p "${WEIGHTS_DIR}"

# ---- Stable Diffusion v1.5 ----
echo "🎨 Downloading Stable Diffusion v1.5..."
if command -v python3 &> /dev/null; then
    python3 -c "
from diffusers import StableDiffusionPipeline
import os

model_id = os.getenv('SD_MODEL_ID', 'runwayml/stable-diffusion-v1-5')
cache_dir = '${WEIGHTS_DIR}'

print(f'  Model: {model_id}')
print(f'  Cache: {cache_dir}')

pipe = StableDiffusionPipeline.from_pretrained(
    model_id,
    cache_dir=cache_dir,
    safety_checker=None,
    requires_safety_checker=False,
)
print('  ✅ Stable Diffusion downloaded')
del pipe
"
else
    echo "  ⚠️  Python3 not found. Skipping SD download."
    echo "     Install: pip install diffusers transformers torch"
fi

# ---- Whisper (tiny model for CPU) ----
echo ""
echo "🎙️ Downloading Whisper (tiny)..."
if command -v python3 &> /dev/null; then
    python3 -c "
import whisper
model = whisper.load_model('tiny', download_root='${WEIGHTS_DIR}/whisper')
print('  ✅ Whisper tiny downloaded')
del model
" 2>/dev/null || echo "  ⚠️  Whisper not installed. Install: pip install openai-whisper"
else
    echo "  ⚠️  Python3 not found."
fi

echo ""
echo "============================================================"
echo "✅ Download complete!"
echo ""
echo "Model weights saved to: ${WEIGHTS_DIR}"
echo ""
echo "To use with Docker Compose, the sd_models volume will"
echo "map these weights into the containers automatically."
echo "============================================================"
