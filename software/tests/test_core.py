#!/usr/bin/env python3
"""Tests unitaires du coeur NOVA (sans dépendance Kivy)."""

import sys
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova import paths
from nova.ui.theme import THEMES, ThemeManager


def test_paths_resolution():
    assert paths.ROOT_DIR.name == "Nova-Project"
    assert paths.SOFTWARE_DIR.exists()
    assert paths.APPS_DIR.exists()


def test_ensure_dirs():
    paths.ensure_dirs()
    assert paths.DATA_DIR.is_dir()
    assert paths.LOGS_DIR.is_dir()


def test_theme_defaults():
    manager = ThemeManager("dark")
    assert manager.current_theme == "dark"
    assert manager.get_color("background") == (0.05, 0.05, 0.08, 1)


def test_theme_switch():
    manager = ThemeManager()
    assert manager.set_theme("cyberpunk") is True
    assert manager.set_theme("inexistant") is False
    assert manager.current_theme == "cyberpunk"


def test_all_themes_share_keys():
    reference = set(THEMES["dark"])
    for name, palette in THEMES.items():
        assert set(palette) == reference, "cles manquantes dans le theme " + name


def test_config_defaults():
    from nova.utils.config_loader import ConfigLoader
    loader = ConfigLoader()
    assert loader.get("device_name") == "NOVA"
    assert "whisper_model" in loader.get("ai", {})
