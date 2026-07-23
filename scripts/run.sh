#!/bin/bash
# Lance NOVA depuis le venv du projet.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

if [ -d venv ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

exec python3 software/nova/main.py
