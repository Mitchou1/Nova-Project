#!/usr/bin/env python3
"""Transitions d'écran NOVA.

Sur Raspberry Pi Zero 2 W, `FadeTransition` rend les deux écrans hors
écran à chaque image : c'est le plus coûteux des transitions Kivy. La
fonction `make_transition()` bascule automatiquement sur un fondu court
ou un simple `NoTransition` selon la configuration.
"""

from kivy.properties import NumericProperty
from kivy.uix.screenmanager import (
    FadeTransition,
    NoTransition,
    SlideTransition,
    SwapTransition,
)

from nova.utils.config_loader import get_config
from nova.utils.platform_utils import is_raspberry_pi


class NovaFadeTransition(FadeTransition):
    """Fondu court, plus nerveux que le réglage par défaut de Kivy."""

    duration = NumericProperty(0.25)


class NovaSlideTransition(SlideTransition):
    """Glissement latéral avec accélération douce."""

    duration = NumericProperty(0.30)

    def __init__(self, **kwargs):
        kwargs.setdefault("direction", "left")
        super(NovaSlideTransition, self).__init__(**kwargs)


TRANSITIONS = {
    "fade": NovaFadeTransition,
    "slide": NovaSlideTransition,
    "swap": SwapTransition,
    "none": NoTransition,
}


def make_transition(name=None):
    """Instancie la transition demandée.

    `name=None` lit `config/system.json` -> "ui": {"transition": "..."}.
    La valeur "auto" donne un glissement sur PC et aucune transition sur Pi.
    """
    if name is None:
        name = get_config().get("ui", {}).get("transition", "auto")

    if name == "auto":
        name = "none" if is_raspberry_pi() else "slide"

    factory = TRANSITIONS.get(name, NovaSlideTransition)
    return factory()
