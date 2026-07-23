#!/usr/bin/env python3
"""Tests unitaires du coeur NOVA (sans dépendance Kivy)."""

import sys
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova import paths


def test_paths_resolution():
    assert paths.ROOT_DIR.name == "Nova-Project"
    assert paths.SOFTWARE_DIR.exists()
    assert paths.APPS_DIR.exists()


def test_ensure_dirs():
    paths.ensure_dirs()
    assert paths.DATA_DIR.is_dir()
    assert paths.LOGS_DIR.is_dir()





def test_config_defaults():
    from nova.utils.config_loader import ConfigLoader
    loader = ConfigLoader()
    assert loader.get("device_name") == "NOVA"
    assert "whisper_model" in loader.get("ai", {})
