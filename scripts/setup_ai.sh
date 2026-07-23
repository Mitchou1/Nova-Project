#!/bin/bash
# Telechargement des modeles IA locaux (Whisper / TinyLlama / Piper).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="$ROOT_DIR/models"

mkdir -p "$MODELS_DIR"
cd "$MODELS_DIR"

echo "== Installation des modeles IA de NOVA =="
echo "Destination : $MODELS_DIR"
echo "Espace requis : environ 1.5 Go"

if [ -d venv ]; then
    # shellcheck disable=SC1091
    source "$ROOT_DIR/venv/bin/activate"
fi

echo "-- Whisper (STT)"
pip install openai-whisper
python3 -c "import whisper; whisper.load_model('tiny')" || \
    echo "Telechargement du modele Whisper au premier usage."

echo "-- llama.cpp (moteur LLM)"
if [ ! -d "$MODELS_DIR/llama.cpp" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
fi
cd "$MODELS_DIR/llama.cpp"
make -j"$(nproc)"
cd "$MODELS_DIR"

echo "-- TinyLlama 1.1B (GGUF Q4_K_M, ~670 Mo)"
if [ ! -f tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf ]; then
    wget -O tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
        "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
fi

echo "-- Piper (TTS) + voix francaise"
pip install piper-tts || echo "piper-tts indisponible via pip, voir les releases GitHub."
if [ ! -f fr_FR-siwis-medium.onnx ]; then
    wget "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
    wget "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json"
fi

echo ""
echo "Modeles IA prets dans $MODELS_DIR"
