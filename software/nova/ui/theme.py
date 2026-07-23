#!/usr/bin/env python3
"""Gestion des thèmes NOVA (aucune dépendance Kivy : testable seul)."""

THEMES = {
    "dark": {
        "background": (0.05, 0.05, 0.08, 1),
        "surface": (0.12, 0.12, 0.18, 1),
        "primary": (0.20, 0.60, 1.00, 1),
        "text": (1, 1, 1, 1),
        "text_secondary": (0.60, 0.60, 0.65, 1),
        "accent": (0.90, 0.30, 0.50, 1),
        "success": (0.20, 0.80, 0.40, 1),
        "warning": (1.00, 0.80, 0.20, 1),
        "error": (1.00, 0.30, 0.30, 1),
    },
    "light": {
        "background": (0.95, 0.95, 0.97, 1),
        "surface": (1, 1, 1, 1),
        "primary": (0.10, 0.50, 0.90, 1),
        "text": (0.10, 0.10, 0.10, 1),
        "text_secondary": (0.40, 0.40, 0.40, 1),
        "accent": (0.80, 0.20, 0.40, 1),
        "success": (0.10, 0.70, 0.30, 1),
        "warning": (0.90, 0.70, 0.10, 1),
        "error": (0.90, 0.20, 0.20, 1),
    },
    "cyberpunk": {
        "background": (0.02, 0.02, 0.05, 1),
        "surface": (0.08, 0.00, 0.15, 1),
        "primary": (0.00, 1.00, 0.80, 1),
        "text": (0.00, 1.00, 0.80, 1),
        "text_secondary": (0.60, 0.20, 0.90, 1),
        "accent": (1.00, 0.00, 0.50, 1),
        "success": (0.00, 1.00, 0.50, 1),
        "warning": (1.00, 0.80, 0.00, 1),
        "error": (1.00, 0.00, 0.20, 1),
    },
}

THEME_NAMES = list(THEMES)

# Correspondance libellé UI -> clé interne
THEME_LABELS = {"Sombre": "dark", "Clair": "light", "Cyber": "cyberpunk"}


class ThemeManager:
    """Fournit les couleurs du thème courant."""

    def __init__(self, theme_name="dark"):
        self.current_theme = theme_name if theme_name in THEMES else "dark"
        self.colors = THEMES[self.current_theme]
        self._listeners = []

    def set_theme(self, theme_name):
        if theme_name not in THEMES:
            return False
        self.current_theme = theme_name
        self.colors = THEMES[theme_name]
        for callback in list(self._listeners):
            try:
                callback(theme_name)
            except Exception as error:
                print("[theme] listener en erreur : {}".format(error))
        return True

    def get_color(self, color_name):
        return self.colors.get(color_name, (1, 1, 1, 1))

    def on_change(self, callback):
        """Enregistre une fonction appelée à chaque changement de thème."""
        self._listeners.append(callback)
        return callback


theme_manager = ThemeManager()
