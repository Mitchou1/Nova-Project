#!/usr/bin/env python3
"""Écran d'accueil NOVA."""

from datetime import datetime

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from nova.ui.app_grid import AppGrid
from nova.ui.status_bar import StatusBar
from nova.ui.theme import theme_manager


class HomeScreen(Screen):
    """Écran principal : salutation, prochain événement, grille d'apps."""

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "home")
        super().__init__(**kwargs)
        self.launcher = None
        self.build_ui()
        Clock.schedule_interval(self.refresh, 60)

    def build_ui(self):
        root = BoxLayout(orientation="vertical", padding=5, spacing=5)

        self.status = StatusBar()
        root.add_widget(self.status)

        main_zone = BoxLayout(orientation="vertical", padding=10, spacing=6)

        self.greeting = Label(
            text=self.greeting_text(), font_size=34, bold=True, size_hint_y=0.18,
            color=theme_manager.get_color("text"),
        )
        main_zone.add_widget(self.greeting)

        self.next_event = Label(
            text="Aucun evenement prevu", font_size=16, size_hint_y=0.10,
            color=theme_manager.get_color("primary"),
        )
        main_zone.add_widget(self.next_event)

        self.app_grid = AppGrid(on_launch=self.launch_app)
        main_zone.add_widget(self.app_grid)

        root.add_widget(main_zone)
        self.add_widget(root)

    # --- API publique ----------------------------------------------------
    def bind_launcher(self, launcher):
        """Relie le launcher : remplit la grille avec les apps chargées."""
        self.launcher = launcher
        self.app_grid.populate(launcher.get_app_info())

    def set_next_event(self, text):
        self.next_event.text = text or "Aucun evenement prevu"

    def launch_app(self, app_id):
        if self.launcher is not None:
            self.launcher.launch_app(app_id)

    # --- interne ---------------------------------------------------------
    def greeting_text(self):
        hour = datetime.now().hour
        if hour < 6:
            return "Bonne nuit"
        if hour < 12:
            return "Bonjour"
        if hour < 18:
            return "Bon apres-midi"
        return "Bonsoir"

    def refresh(self, dt=None):
        self.greeting.text = self.greeting_text()
        self.refresh_next_event()

    def refresh_next_event(self):
        try:
            from apps.calendar.storage import next_event_label
            self.set_next_event(next_event_label())
        except Exception:
            pass
