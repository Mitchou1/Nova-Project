#!/usr/bin/env python3
"""Chargement et sauvegarde de la configuration système."""

import json

from nova.paths import SYSTEM_CONFIG, SYSTEM_CONFIG_LOCAL

DEFAULT_CONFIG = {
    "device_name": "NOVA",
    "version": "0.1.0",
    "screen": {"width": 800, "height": 480, "rotation": 0},
    "theme": "classic",
    "language": "fr",
    "wifi": {"auto_connect": True},
    "power": {"low_battery_threshold": 15, "auto_sleep_minutes": 5},
    "audio": {"volume": 70, "brightness": 80},
    "ui": {"particles": "auto", "waveform": "auto", "animations": "auto", "transition": "auto"},
    "map": {
        "provider": "maptiler",
        "style": "streets-v2-dark",
        "api_key": "",
        "online": True,
    },
    "ai": {
        "whisper_model": "tiny",
        "llm_model": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "tts_voice": "fr_FR-siwis-medium.onnx",
    },
}


def _merge(defaults, loaded):
    result = dict(defaults)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _strip_overlay(config, overlay):
    """Copie de `config` sans les cles presentes dans `overlay` (recursif).

    Sans ca, save() reecrirait les secrets de system.local.json dans
    system.json (suivi par git) des le premier changement de reglage —
    exactement le bug que la surcharge locale est censee eviter.
    """
    result = {}
    for key, value in config.items():
        if key not in overlay:
            result[key] = value
            continue
        ov = overlay[key]
        if isinstance(value, dict):
            if isinstance(ov, dict):
                stripped = _strip_overlay(value, ov)
                if stripped:
                    result[key] = stripped
                # sinon : sous-dict entierement couvert par l'overlay, omis
            else:
                # Overlay malformee (valeur scalaire la ou `value` est un
                # dict) : impossible de savoir quelle cle du sous-dict est
                # censee etre couverte, donc on garde `value` telle quelle
                # plutot que de perdre toute une section (ex. "map") de
                # system.json.
                result[key] = value
        # sinon : valeur scalaire couverte par l'overlay, omise
    return result


class ConfigLoader:
    def __init__(self, config_path=None):
        self.config_path = config_path or SYSTEM_CONFIG
        self._local_overlay = self._load_local_overlay()
        self.config = self.load()

    def load(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                config = _merge(DEFAULT_CONFIG, json.load(handle))
        except (OSError, ValueError) as error:
            print("[config] lecture impossible ({}), valeurs par defaut".format(error))
            config = dict(DEFAULT_CONFIG)
        return _merge(config, self._local_overlay)

    @staticmethod
    def _load_local_overlay():
        """Cles API/secrets (map.api_key, map.ors_key...) : audit securite —
        elles etaient en clair dans system.json, deja committees sur GitHub.
        Desormais lues depuis system.local.json (non suivi par git), fusion
        par-dessus la config normale. Absent = simplement ignore."""
        try:
            with open(SYSTEM_CONFIG_LOCAL, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value, save=True):
        self.config[key] = value
        if save:
            self.save()

    def save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            # Ne jamais reecrire les secrets de la surcharge locale dans le
            # fichier suivi par git (system.json).
            to_write = _strip_overlay(self.config, self._local_overlay)
            with open(self.config_path, "w", encoding="utf-8") as handle:
                json.dump(to_write, handle, indent=4, ensure_ascii=False)
            return True
        except OSError as error:
            print("[config] sauvegarde impossible : {}".format(error))
            return False


_instance = None


def get_config():
    global _instance
    if _instance is None:
        _instance = ConfigLoader()
    return _instance
