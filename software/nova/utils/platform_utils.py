#!/usr/bin/env python3
"""Détection de la plateforme d'exécution."""

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
