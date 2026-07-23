#!/usr/bin/env python3
"""Tests du launcher (ignorés si Kivy n'est pas installé)."""

import os
import sys
from pathlib import Path

import pytest

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova.launcher import AppLauncher


def display_available():
    """Kivy exige une fenetre : X11, Wayland ou framebuffer."""
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return True
    return Path("/dev/fb0").exists()


class FakeScreenManager:
    def __init__(self):
        self.widgets = []
        self.current = "home"

    def add_widget(self, widget):
        self.widgets.append(widget)


def test_discovery_finds_all_apps():
    launcher = AppLauncher(FakeScreenManager())
    found = launcher.discover_apps()
    for expected in ("assistant", "calendar", "maps", "radio", "sensors", "settings"):
        assert expected in found


@pytest.mark.skipif(not display_available(), reason="aucun affichage disponible")
def test_load_all_apps():
    pytest.importorskip("kivy")
    manager = FakeScreenManager()
    launcher = AppLauncher(manager)
    count = launcher.load_all_apps()
    assert count == len(launcher.discover_apps())
    assert launcher.launch_app("settings") is True
    assert manager.current == "settings"
