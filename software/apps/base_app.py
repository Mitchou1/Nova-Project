#!/usr/bin/env python3
"""Classe de base de toutes les applications NOVA.

Chaque application doit :
  - hériter de BaseApp
  - définir app_name, app_icon, app_id
  - exporter `NovaApp = MaClasse` à la fin du module
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from nova.ui.theme import theme_manager


class BaseApp(Screen):
    """Écran d'application avec en-tête et bouton retour."""

    app_name = "Application"
    app_icon = "•"
    app_id = "base"

    def __init__(self, **kwargs):
        kwargs.setdefault("name", self.app_id)
        super().__init__(**kwargs)
        self.content = None
        self.build_ui()

    def build_ui(self):
        """Construit l'ossature. Les sous-classes appellent super() puis
        remplissent self.content."""
        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        header = BoxLayout(size_hint_y=0.13, spacing=10)
        back = Button(
            text="< Retour", size_hint_x=0.28, font_size=16,
            background_normal="", background_color=theme_manager.get_color("surface"),
        )
        back.bind(on_press=self.go_home)
        header.add_widget(back)

        header.add_widget(Label(
            text="{} {}".format(self.app_icon, self.app_name),
            font_size=22, bold=True, color=theme_manager.get_color("text"),
        ))
        root.add_widget(header)

        self.content = BoxLayout(orientation="vertical", spacing=8)
        root.add_widget(self.content)

        self.add_widget(root)

    def go_home(self, *_):
        if self.manager is not None:
            self.manager.current = "home"

    def on_cleanup(self):
        """Appelé à l'arrêt de NOVA. À surcharger si besoin."""
        return None
