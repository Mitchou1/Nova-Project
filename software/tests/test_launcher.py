#!/usr/bin/env python3
"""
Tests du launcher
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_launcher_import():
    """Test d'import du launcher"""
    try:
        from nova.launcher import AppLauncher
        assert True
    except ImportError:
        assert False, "Impossible d'importer AppLauncher"

def test_theme_manager():
    """Test du gestionnaire de thèmes"""
    from nova.ui.theme import ThemeManager
    tm = ThemeManager("dark")
    assert tm.current_theme == "dark"
    assert tm.get_color("background") == (0.05, 0.05, 0.08, 1)
