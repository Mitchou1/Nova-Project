#!/usr/bin/env python3
"""Détection de la plateforme d'exécution et état des interfaces sans fil."""

import glob
import os
import shutil
from pathlib import Path

_cache = {}


def is_raspberry_pi():
    if "is_pi" in _cache:
        return _cache["is_pi"]
    result = False
    for candidate in ("/proc/device-tree/model", "/proc/cpuinfo"):
        try:
            text = Path(candidate).read_text(errors="ignore").lower()
        except OSError:
            continue
        if "raspberry pi" in text:
            result = True
            break
    _cache["is_pi"] = result
    return result


def has_command(name):
    return shutil.which(name) is not None


def simulation_mode():
    return not is_raspberry_pi()


def wifi_state():
    """Retourne "up", "down" ou "none" selon l'état des interfaces sans fil."""
    interfaces = glob.glob("/sys/class/net/wl*")
    if not interfaces:
        return "none"
    for interface in interfaces:
        try:
            with open(os.path.join(interface, "operstate"), "r") as handle:
                if handle.read().strip() == "up":
                    return "up"
        except OSError:
            continue
    return "down"


def bluetooth_state():
    """Retourne "up", "down" ou "none" selon les contrôleurs Bluetooth.

    Audit : `open()` ne fait pas d'expansion de glob ("rfkill*/state" était
    passé tel quel comme nom de fichier) — l'ouverture echouait donc
    toujours, l'erreur etait avalee, et la fonction renvoyait "up" sans
    condition des le premier controleur trouve, meme Bluetooth eteint via
    Reglages (bluetoothctl power off). `glob.glob()` resout d'abord le vrai
    chemin du fichier d'etat rfkill, dont le contenu ("1"/"0") reflete
    l'etat reel (kernel : 1 = actif, 0 = bloque).
    """
    controllers = glob.glob("/sys/class/bluetooth/hci*")
    if not controllers:
        return "none"
    for controller in controllers:
        for state_path in glob.glob(os.path.join(controller, "rfkill*/state")):
            try:
                with open(state_path, "r") as handle:
                    if handle.read().strip() == "1":
                        return "up"
            except OSError:
                continue
    return "down"
