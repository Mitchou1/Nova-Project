#!/bin/bash
set -e

echo "🚀 Installation de NOVA..."

if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "⚠️  Ce script doit être exécuté sur un Raspberry Pi"
    exit 1
fi

echo "📦 Mise à jour du système..."
sudo apt update && sudo apt full-upgrade -y

echo "🔧 Installation des dépendances système..."
sudo apt install -y \
    python3-pip python3-venv \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev \
    zlib1g-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-tools \
    libmtdev-dev xclip xsel libjpeg-dev \
    i2c-tools gpsd gpsd-clients python3-gps \
    git

echo "⚡ Activation des interfaces..."
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_serial 0
sudo raspi-config nonint do_camera 0

echo "🐍 Création de l'environnement virtuel..."
cd /home/pi/nova
python3 -m venv venv
source venv/bin/activate

echo "📚 Installation des dépendances Python..."
pip install --upgrade pip
pip install -r requirements.txt

echo "📁 Création de la structure de données..."
mkdir -p /home/pi/nova/data/{map_tiles,logs,models}

echo "✅ Installation terminée !"
echo ""
echo "Pour démarrer NOVA :"
echo "  cd /home/pi/nova"
echo "  source venv/bin/activate"
echo "  python software/nova/main.py"
