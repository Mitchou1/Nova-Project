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
    """Retourne "up", "down" ou "none" selon les contrôleurs Bluetooth."""
    controllers = glob.glob("/sys/class/bluetooth/hci*")
    if not controllers:
        return "none"
    for controller in controllers:
        try:
            with open(os.path.join(controller, "rfkill*/state"), "r") as handle:
                handle.read()
        except (OSError, IOError):
            pass
        return "up"
    return "down"
