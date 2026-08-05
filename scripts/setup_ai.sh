#!/bin/bash
echo "Installation des modèles IA..."
cd /home/pi/nova/models

# Whisper (téléchargé automatiquement au premier usage)

# Télécharger TinyLlama
echo "Téléchargement de TinyLlama..."
wget -O tinyllama.gguf "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

# Télécharger voix Piper FR
echo "Téléchargement de la voix Piper FR..."
wget "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR-siwis-medium.onnx"
wget "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR-siwis-medium.onnx.json"

echo "✅ Modèles IA prêts"
