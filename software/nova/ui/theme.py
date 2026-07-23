#!/usr/bin/env python3
"""Gestion des thèmes NOVA.

API principale
--------------
    from nova.ui.theme import theme

    theme.set_theme("nova_amber")
    theme.get_color("primary")            -> "#F59E0B"
    theme.get_rgba("primary")             -> (0.96, 0.62, 0.04, 1.0)
    theme.get_rgba("glass")               -> (0.96, 0.62, 0.04, 0.08)
    theme.get_rgba("#FFFFFF", 0.25)       -> (1.0, 1.0, 1.0, 0.25)
    theme.list_themes()                   -> ["nova_dark", "nova_amber", ...]

Réaction aux changements de thème :

    theme.bind(on_theme_change=lambda _t, name: rebuild_ui())

Kivy est optionnel : si `kivy.event` est introuvable (CI, tests headless),
un dispatcher minimal prend le relais et le module reste importable seul.
"""

import re

try:
    from kivy.event import EventDispatcher
except ImportError:  # pragma: no cover - chemin utilisé en CI sans Kivy
    class EventDispatcher(object):
        """Repli minimal : bind / unbind / dispatch d'événements nommés.

        Le registre est créé à la demande : Kivy initialise le sien au niveau C
        avant `__init__`, et `register_event_type()` est donc appelé avant que
        `super().__init__()` n'ait pu s'exécuter.
        """

        def _registry(self):
            if not hasattr(self, "_handlers"):
                self._handlers = {}
            return self._handlers

        def __init__(self, **kwargs):
            self._registry()

        def register_event_type(self, event_name):
            self._registry().setdefault(event_name, [])

        def bind(self, **kwargs):
            for event_name, callback in kwargs.items():
                self._registry().setdefault(event_name, []).append(callback)

        def unbind(self, **kwargs):
            for event_name, callback in kwargs.items():
                if callback in self._registry().get(event_name, []):
                    self._registry()[event_name].remove(callback)

        def dispatch(self, event_name, *args):
            handler = getattr(self, event_name, None)
            if callable(handler):
                handler(*args)
            for callback in list(self._registry().get(event_name, [])):
                callback(self, *args)


# ---------------------------------------------------------------------------
# Analyse des couleurs
# ---------------------------------------------------------------------------
# Tolère : "rgba(255, 255, 255, 0.06)", "rgb( 20,184,166 )", "RGBA(0,0,0,.5)"
# Les \s* sont placés des DEUX côtés de chaque virgule et après la parenthèse
# ouvrante : c'est là que la plupart des regex de ce type échouent.
RGBA_PATTERN = re.compile(
    r"^\s*rgba?\(\s*"
    r"([\d.]+)\s*,\s*"
    r"([\d.]+)\s*,\s*"
    r"([\d.]+)\s*"
    r"(?:,\s*([\d.]+)\s*)?"
    r"\)\s*$",
    re.IGNORECASE,
)

HEX_PATTERN = re.compile(r"^\s*#?([0-9a-fA-F]{3,8})\s*$")


def hex_to_rgba(value, alpha=1.0):
    """Convertit "#RRGGBB" en tuple Kivy (r, g, b, a) normalisé 0..1.

    Formats acceptés : #RGB, #RGBA, #RRGGBB, #RRGGBBAA (avec ou sans '#').
    L'alpha éventuellement porté par la couleur est multiplié par `alpha`.
    """
    match = HEX_PATTERN.match(str(value))
    if match is None:
        raise ValueError("couleur hexadecimale invalide : {!r}".format(value))

    digits = match.group(1)

    if len(digits) in (3, 4):                       # forme courte : #ABC
        digits = "".join(char * 2 for char in digits)
    if len(digits) not in (6, 8):
        raise ValueError("couleur hexadecimale invalide : {!r}".format(value))

    red = int(digits[0:2], 16) / 255.0
    green = int(digits[2:4], 16) / 255.0
    blue = int(digits[4:6], 16) / 255.0
    embedded = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0

    return (red, green, blue, embedded * float(alpha))


def rgba_string_to_rgba(value, alpha=1.0):
    """Convertit "rgba(r, g, b, a)" en tuple Kivy normalisé 0..1."""
    match = RGBA_PATTERN.match(str(value))
    if match is None:
        raise ValueError("chaine rgba() invalide : {!r}".format(value))

    red, green, blue, embedded = match.groups()
    embedded = 1.0 if embedded is None else float(embedded)

    return (
        float(red) / 255.0,
        float(green) / 255.0,
        float(blue) / 255.0,
        embedded * float(alpha),
    )


def parse_color(value, alpha=1.0):
    """Point d'entrée universel : HEX, rgba(), ou tuple/liste déjà normalisé."""
    if isinstance(value, (tuple, list)):
        components = [float(channel) for channel in value]
        if len(components) == 3:
            components.append(1.0)
        if len(components) != 4:
            raise ValueError("tuple couleur invalide : {!r}".format(value))
        components[3] *= float(alpha)
        return tuple(components)

    text = str(value).strip()
    if text.lower().startswith(("rgba(", "rgb(")):
        return rgba_string_to_rgba(text, alpha)
    return hex_to_rgba(text, alpha)


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------
REQUIRED_KEYS = frozenset({
    "primary", "secondary", "accent",
    "background", "surface", "surface_light",
    "text_primary", "text_secondary",
    "success", "warning", "error",
    "glass", "glass_border",
    "gradient_start", "gradient_end",
})

THEMES = {
    "nova_dark": {
        "primary": "#3B82F6",
        "secondary": "#8B5CF6",
        "accent": "#06B6D4",
        "background": "#0A0A0F",
        "surface": "#14141F",
        "surface_light": "#1E1E2E",
        "text_primary": "#FFFFFF",
        "text_secondary": "#9CA3AF",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "error": "#EF4444",
        "glass": "rgba(255, 255, 255, 0.06)",
        "glass_border": "rgba(255, 255, 255, 0.14)",
        "gradient_start": "#3B82F6",
        "gradient_end": "#8B5CF6",
    },
    "nova_amber": {
        "primary": "#F59E0B",
        "secondary": "#B45309",
        "accent": "#FCD34D",
        "background": "#0F0A05",
        "surface": "#1C1408",
        "surface_light": "#2A1F0F",
        "text_primary": "#FFF7ED",
        "text_secondary": "#C9A87C",
        "success": "#84CC16",
        "warning": "#FB923C",
        "error": "#DC2626",
        "glass": "rgba(245, 158, 11, 0.08)",
        "glass_border": "rgba(252, 211, 77, 0.22)",
        "gradient_start": "#F59E0B",
        "gradient_end": "#7C2D12",
    },
    "nova_ocean": {
        "primary": "#14B8A6",
        "secondary": "#0EA5E9",
        "accent": "#2DD4BF",
        "background": "#04121A",
        "surface": "#0A1E2B",
        "surface_light": "#123141",
        "text_primary": "#ECFEFF",
        "text_secondary": "#7DA6B8",
        "success": "#10B981",
        "warning": "#FBBF24",
        "error": "#F43F5E",
        "glass": "rgba(20, 184, 166, 0.08)",
        "glass_border": "rgba(45, 212, 191, 0.20)",
        "gradient_start": "#0EA5E9",
        "gradient_end": "#14B8A6",
    },
    "nova_purple": {
        "primary": "#A855F7",
        "secondary": "#6366F1",
        "accent": "#EC4899",
        "background": "#0B0614",
        "surface": "#170F24",
        "surface_light": "#241634",
        "text_primary": "#F5F3FF",
        "text_secondary": "#A99BC4",
        "success": "#34D399",
        "warning": "#FBBF24",
        "error": "#FB7185",
        "glass": "rgba(168, 85, 247, 0.09)",
        "glass_border": "rgba(236, 72, 153, 0.22)",
        "gradient_start": "#A855F7",
        "gradient_end": "#EC4899",
    },
}

DEFAULT_THEME = "nova_dark"

# Libellés affichés dans l'application Réglages
THEME_LABELS = {
    "Nuit": "nova_dark",
    "Ambre": "nova_amber",
    "Ocean": "nova_ocean",
    "Violet": "nova_purple",
}


def validate_themes(themes=None):
    """Vérifie que chaque thème expose toutes les clés obligatoires."""
    problems = []
    for name, palette in (themes or THEMES).items():
        missing = REQUIRED_KEYS - set(palette)
        extra = set(palette) - REQUIRED_KEYS
        if missing:
            problems.append("{} : clefs manquantes {}".format(name, sorted(missing)))
        if extra:
            problems.append("{} : clefs inconnues {}".format(name, sorted(extra)))
    return problems


# ---------------------------------------------------------------------------
# Gestionnaire de thème
# ---------------------------------------------------------------------------
class NovaTheme(EventDispatcher):
    """Thème actif de NOVA, diffusé via l'événement `on_theme_change`."""

    def __init__(self, theme_name=DEFAULT_THEME, **kwargs):
        self.register_event_type("on_theme_change")
        super(NovaTheme, self).__init__(**kwargs)

        self.name = theme_name if theme_name in THEMES else DEFAULT_THEME
        self.palette = THEMES[self.name]

    # --- sélection -------------------------------------------------------
    def set_theme(self, name):
        """Active un thème. Retourne False si le nom est inconnu."""
        if name not in THEMES:
            print("[theme] thème inconnu : {}".format(name))
            return False
        if name == self.name:
            return True

        self.name = name
        self.palette = THEMES[name]
        self.dispatch("on_theme_change", name)
        return True

    def list_themes(self):
        """Noms des thèmes disponibles."""
        return list(THEMES)

    def labels(self):
        """Correspondance libellé affiché -> nom interne."""
        return dict(THEME_LABELS)

    # --- lecture des couleurs -------------------------------------------
    def get_color(self, key, default="#FFFFFF"):
        """Valeur brute du thème : "#RRGGBB", ou "rgba(...)" pour le verre."""
        return self.palette.get(key, default)

    def get_rgba(self, color, alpha=1.0):
        """Tuple Kivy (r, g, b, a) à partir d'une clé, d'un HEX ou d'un rgba().

        `alpha` **multiplie** l'opacité d'origine : `get_rgba("glass")` conserve
        donc les 6 % du verre, et `get_rgba("glass", 0.5)` les ramène à 3 %.
        """
        value = self.palette.get(color, color) if isinstance(color, str) else color
        try:
            return parse_color(value, alpha)
        except ValueError as error:
            print("[theme] {}".format(error))
            return (1.0, 1.0, 1.0, float(alpha))

    def get_gradient(self, alpha=1.0):
        """Couple (début, fin) du dégradé du thème, en RGBA."""
        return (self.get_rgba("gradient_start", alpha),
                self.get_rgba("gradient_end", alpha))

    def as_rgba_dict(self, alpha=1.0):
        """Palette complète convertie en tuples Kivy."""
        return {key: self.get_rgba(key, alpha) for key in self.palette}

    # --- événement --------------------------------------------------------
    def on_theme_change(self, theme_name):
        """Gestionnaire par défaut (obligatoire pour EventDispatcher)."""
        return None


# Instance globale : à importer partout dans l'application
theme = NovaTheme()


# ---------------------------------------------------------------------------
# Compatibilité avec l'ancienne API (`theme_manager.get_color()` -> tuple)
# ---------------------------------------------------------------------------
# Conservé pour que les écrans déjà écrits continuent de fonctionner pendant
# la migration. À supprimer une fois tous les appels passés à `theme`.
LEGACY_KEY_ALIASES = {"text": "text_primary"}
LEGACY_THEME_ALIASES = {
    "dark": "nova_dark",
    "light": "nova_ocean",
    "cyberpunk": "nova_purple",
}

THEME_NAMES = list(THEMES)


class ThemeManager(object):
    """Adaptateur : expose l'ancienne API en tuples RGBA."""

    def __init__(self, theme_name=DEFAULT_THEME, source=None):
        self._theme = source or theme
        self.set_theme(theme_name)

    @property
    def current_theme(self):
        return self._theme.name

    @property
    def colors(self):
        return self._theme.as_rgba_dict()

    def set_theme(self, theme_name):
        resolved = LEGACY_THEME_ALIASES.get(theme_name, theme_name)
        return self._theme.set_theme(resolved)

    def get_color(self, color_name):
        key = LEGACY_KEY_ALIASES.get(color_name, color_name)
        if key not in self._theme.palette:
            return (1.0, 1.0, 1.0, 1.0)
        return self._theme.get_rgba(key)

    def on_change(self, callback):
        """Ancien système d'abonnement, redirigé vers l'événement Kivy."""
        self._theme.bind(on_theme_change=lambda _dispatcher, name: callback(name))
        return callback


theme_manager = ThemeManager()
