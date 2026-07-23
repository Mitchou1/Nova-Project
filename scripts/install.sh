#!/bin/bash
# Installation complete de NOVA sur Raspberry Pi OS.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "== Installation de NOVA =="
echo "Dossier du projet : $ROOT_DIR"

IS_PI=0
if grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
    IS_PI=1
elif grep -qi "raspberry pi" /proc/cpuinfo 2>/dev/null; then
    IS_PI=1
fi

if [ "$IS_PI" -eq 0 ]; then
    echo "Materiel non-Raspberry detecte : installation en mode developpement."
fi

echo "-- Mise a jour du systeme"
sudo apt update

SYS_PKGS=(
    git python3-pip python3-venv python3-dev
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
    libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev
    zlib1g-dev libjpeg-dev libmtdev-dev
    libgstreamer1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good
    alsa-utils fonts-noto-color-emoji fonts-dejavu-core
)

if [ "$IS_PI" -eq 1 ]; then
    SYS_PKGS+=(i2c-tools gpsd gpsd-clients python3-gps)
fi

echo "-- Installation des dependances systeme"
sudo apt install -y "${SYS_PKGS[@]}"

if [ "$IS_PI" -eq 1 ] && command -v raspi-config >/dev/null 2>&1; then
    echo "-- Activation des interfaces (SPI, I2C, UART)"
    sudo raspi-config nonint do_spi 0
    sudo raspi-config nonint do_i2c 0
    sudo raspi-config nonint do_serial 2 || true
fi

echo "-- Environnement virtuel Python"
cd "$ROOT_DIR"
if [ ! -d venv ]; then
    python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

echo "-- Dependances Python"
pip install --upgrade pip wheel
pip install -r requirements.txt

if [ "$IS_PI" -eq 1 ]; then
    pip install -r requirements-pi.txt
fi

echo "-- Creation des dossiers runtime"
mkdir -p "$ROOT_DIR/data/map_tiles" "$ROOT_DIR/data/logs" "$ROOT_DIR/models"

echo ""
echo "Installation terminee."
echo "Lancement :  ./scripts/run.sh"
echo "Modeles IA :  ./scripts/setup_ai.sh"
