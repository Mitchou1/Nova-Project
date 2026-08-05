#!/usr/bin/env python3
"""Polices et icônes NOVA.

Enregistre les polices du design (Sora, Hanken Grotesk, JetBrains Mono) et la
police d'icônes Material Symbols auprès de Kivy, puis expose :

  - des noms de police utilisables dans un Label : font_name="Sora" / "Body"
    / "Mono" / "Icons"
  - la fonction `icon("radio")` qui renvoie le CARACTÈRE à afficher avec la
    police "Icons".

Pourquoi un caractère et pas le nom ? Les Material Symbols associent le nom
(« radio ») à un glyphe via une ligature, et le moteur de rendu de Kivy (SDL2)
ne gère pas les ligatures. On passe donc par le point de code Unicode direct,
seul moyen fiable d'afficher l'icône.
"""

from pathlib import Path

from kivy.core.text import LabelBase

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"

# Noms logiques -> fichiers. "Display"/"Body"/"Mono" suivent le DESIGN.md.
_FONT_FILES = {
    "Sora": {
        "fn_regular": "Sora-Regular.ttf",
        "fn_bold": "Sora-Bold.ttf",
    },
    "SoraExtra": {
        "fn_regular": "Sora-ExtraBold.ttf",
    },
    "Body": {
        "fn_regular": "HankenGrotesk-Regular.ttf",
        "fn_bold": "HankenGrotesk-Bold.ttf",
    },
    "Mono": {
        "fn_regular": "JetBrainsMono-Regular.ttf",
        "fn_bold": "JetBrainsMono-Bold.ttf",
    },
    "Icons": {
        "fn_regular": "MaterialSymbolsOutlined.ttf",
    },
}

# Alias lisibles pour le code d'interface
FONT_DISPLAY = "Sora"       # horloge, titres
FONT_DISPLAY_XL = "SoraExtra"
FONT_BODY = "Body"          # texte courant
FONT_MONO = "Mono"          # données techniques, mode Undercover
FONT_ICON = "Icons"         # icônes Material

# Nom d'icône -> caractère Unicode (extrait de la police fournie).
ICONS = {
    "air": "\uefd8",
    "arrow_back": "\ue5c4",
    "auto_awesome": "\ue65f",
    "battery_charging_full": "\ue1a3",
    "battery_full": "\ue1a5",
    "bluetooth": "\ue1a7",
    "bolt": "\uea0b",
    "calendar_today": "\ue935",
    "chevron_right": "\ue5cc",
    "close": "\ue5cd",
    "event_note": "\ue616",
    "explore": "\ue87a",
    "graphic_eq": "\ue1b8",
    "home": "\ue9b2",
    "map": "\ue55b",
    "memory": "\ue322",
    "mic": "\ue31d",
    "my_location": "\ue55c",
    "navigation": "\ue55d",
    "palette": "\ue40a",
    "person": "\uf0d3",
    "play_arrow": "\ue037",
    "radio": "\ue03e",
    "search": "\uef7a",
    "sensors": "\ue51e",
    "settings": "\ue8b8",
    "settings_input_component": "\ue8c1",
    "shield": "\ue9e0",
    "signal_wifi_4_bar": "\uf065",
    "smart_toy": "\uf06c",
    "stop": "\ue047",
    "terminal": "\ueb8e",
    "thermostat": "\uf076",
    "visibility_off": "\ue8f5",
    "water_drop": "\ue798",
    "add": "\ue145",
    "add_circle": "\ue990",
    "brightness_6": "\ue3ab",
    "chevron_left": "\ue5cb",
    "circle": "\uef4a",
    "delete": "\ue92e",
    "edit": "\uf097",
    "fiber_manual_record": "\ue061",
    "notifications": "\ue7f5",
    "restart_alt": "\uf053",
    "speed": "\ue9e4",
    "stop": "\ue047",
    "today": "\ue8df",
    "volume_up": "\ue050",
    "warning": "\uf083",
    "wifi": "\ue63e",
    # --- Camera et medias (ajoutees : elles manquaient et donnaient du tofu)
    "photo_camera": "\ue412",
    "camera_alt": "\ue3b0",
    "collections": "\ue3b6",
    "photo_library": "\ue413",
    "image": "\ue3f4",
    "folder": "\ue2c7",
    # --- Explorateur de fichiers
    "more_vert": "\ue5d4",
    "arrow_upward": "\ue5d8",
    "create_new_folder": "\ue2cc",
    "drive_file_rename_outline": "\ue9b1",
    # --- Types de fichiers
    "description": "\ue873",
    "audiotrack": "\ue3a1",
    "movie": "\ue02c",
    "insert_drive_file": "\ue24d",
    "note_add": "\ue89c",
    "content_copy": "\ue14d",
    "content_paste": "\ue14f",
    "content_cut": "\ue14e",
    "download": "\ue2c4",
}

_registered = False


def register_fonts():
    """Enregistre toutes les polices auprès de Kivy (idempotent).

    Si un fichier manque, la police correspondante est ignorée avec un
    avertissement plutôt que de planter : l'interface reste utilisable, elle
    retombe simplement sur la police par défaut.
    """
    global _registered
    if _registered:
        return True

    for name, files in _FONT_FILES.items():
        kwargs = {}
        ok = True
        for slot, filename in files.items():
            path = FONTS_DIR / filename
            if not path.exists():
                print("[fonts] manquant : {} (police '{}' ignoree)".format(path, name))
                ok = False
                break
            kwargs[slot] = str(path)
        if ok:
            LabelBase.register(name=name, **kwargs)

    _registered = True
    return True


def icon(name, fallback="\ue5cd"):
    """Caractère à afficher avec la police "Icons" pour l'icône demandée.

    Exemple :
        Label(text=icon("radio"), font_name=FONT_ICON, font_size=dp(28))
    """
    return ICONS.get(name, fallback)


def has_icon(name):
    return name in ICONS


# ─────────────────────────────────────────────────────────────────────────
# Filet de securite : une icone jamais declaree renvoyait un carre vide
# (« tofu »). On previent desormais dans la console, avec le nom fautif,
# pour la corriger tout de suite au lieu de la decouvrir a l'ecran.
# ─────────────────────────────────────────────────────────────────────────
_manquantes_signalees = set()


def icon_safe(name, fallback="help"):
    """Comme icon(), mais previent si le nom n'existe pas.

    A utiliser pour toute icone dont le nom vient d'une variable
    (identifiant d'app, donnee de config...) plutot que d'un litteral.
    """
    if has_icon(name):
        return ICONS[name]
    if name not in _manquantes_signalees:
        _manquantes_signalees.add(name)
        print("[fonts] icone inconnue : '{}' — ajoutez-la dans ICONS "
              "(sinon un carre vide s'affichera)".format(name))
    return ICONS.get(fallback, "\ue5cd")
