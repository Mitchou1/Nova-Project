#!/usr/bin/env python3
"""Résolution centralisée des chemins du projet NOVA."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SOFTWARE_DIR = ROOT_DIR / "software"
NOVA_DIR = SOFTWARE_DIR / "nova"
APPS_DIR = SOFTWARE_DIR / "apps"
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
LOGS_DIR = DATA_DIR / "logs"
MAP_TILES_DIR = DATA_DIR / "map_tiles"
MAPS_DATA_DIR = ROOT_DIR / "maps_data"
SYSTEM_CONFIG = CONFIG_DIR / "system.json"
CALENDAR_DB = DATA_DIR / "calendar.db"

_RUNTIME_DIRS = (DATA_DIR, LOGS_DIR, MAP_TILES_DIR, MODELS_DIR)


def ensure_dirs():
    for directory in _RUNTIME_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
    return True
