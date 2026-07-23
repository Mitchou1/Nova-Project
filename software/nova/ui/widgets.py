#!/usr/bin/env python3
"""Widgets réutilisables NOVA."""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle

from nova.ui.theme import theme_manager


class Card(BoxLayout):
    """Conteneur à fond arrondi."""

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", 15)
        kwargs.setdefault("spacing", 10)
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*theme_manager.get_color("surface"))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15])
        self.bind(pos=self._refresh, size=self._refresh)

    def _refresh(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class IconButton(Button):
    """Bouton plat avec icône."""

    def __init__(self, icon="•", text="", **kwargs):
        kwargs.setdefault("font_size", 20)
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_color", theme_manager.get_color("surface"))
        super().__init__(text="{} {}".format(icon, text).strip(), **kwargs)


class TitleLabel(Label):
    """Titre de section."""

    def __init__(self, text="", **kwargs):
        kwargs.setdefault("font_size", 20)
        kwargs.setdefault("bold", True)
        kwargs.setdefault("color", theme_manager.get_color("text"))
        super().__init__(text=text, **kwargs)
