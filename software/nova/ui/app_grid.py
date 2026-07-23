#!/usr/bin/env python3
"""Grille d'applications de l'écran d'accueil."""

from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle

from nova.ui.theme import theme_manager


class AppButton(Button):
    """Tuile d'application."""

    def __init__(self, app_id, app_name, app_icon="•", **kwargs):
        kwargs.setdefault("font_size", 17)
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("valign", "middle")
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        super().__init__(text="{}\n{}".format(app_icon, app_name), **kwargs)

        self.app_id = app_id
        with self.canvas.before:
            self._color = Color(*theme_manager.get_color("surface"))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[12])
        self.bind(pos=self._refresh, size=self._refresh)

    def _refresh(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self.text_size = (self.width * 0.9, None)


class AppGrid(GridLayout):
    """Affiche les applications découvertes par le launcher."""

    def __init__(self, on_launch=None, **kwargs):
        kwargs.setdefault("cols", 3)
        kwargs.setdefault("spacing", 14)
        kwargs.setdefault("padding", 16)
        kwargs.setdefault("size_hint_y", 0.62)
        super().__init__(**kwargs)
        self.on_launch = on_launch
        self.apps = []

    def populate(self, apps_info):
        self.clear_widgets()
        self.apps = list(apps_info or [])

        if not self.apps:
            self.add_widget(Label(
                text="Aucune application detectee",
                color=theme_manager.get_color("text_secondary"),
            ))
            return

        for app in self.apps:
            button = AppButton(app["id"], app["name"], app.get("icon", "•"))
            button.bind(on_press=self._handle_press)
            self.add_widget(button)

    def _handle_press(self, instance):
        if callable(self.on_launch):
            self.on_launch(instance.app_id)
