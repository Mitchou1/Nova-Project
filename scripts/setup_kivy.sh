#!/bin/bash
# Installation / reinstallation de Kivy seul.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"
if [ -d venv ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

pip install --upgrade pip wheel
pip install "kivy[base]==2.3.0"

echo "Kivy installe. Test rapide :"
python3 -c "import kivy; print('Kivy', kivy.__version__)"
