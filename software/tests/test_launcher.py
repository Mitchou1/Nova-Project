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
    """Test du gestionnaire de thèmes.

    "dark" est un ALIAS legacy (LEGACY_THEME_ALIASES dans theme.py, garde
    pour que les ecrans deja ecrits avant la migration vers classic/
    cyberpunk/undercover continuent de fonctionner) : current_theme renvoie
    le nom RESOLU ("classic"), pas l'alias passe au constructeur.
    """
    from nova.ui.theme import THEMES, ThemeManager, hex_to_rgba
    tm = ThemeManager("dark")
    assert tm.current_theme == "classic"
    assert tm.get_color("background") == hex_to_rgba(THEMES["classic"]["background"])
