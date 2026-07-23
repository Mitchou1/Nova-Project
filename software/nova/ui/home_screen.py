#!/usr/bin/env python3
"""Écran d'accueil NOVA — design glassmorphism.

La grille d'applications reste alimentée par `AppLauncher` : ajouter un
dossier dans `software/apps/` suffit toujours pour voir apparaître une
tuile, sans toucher à ce fichier.
"""

import math
from datetime import datetime

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from nova.ui.status_bar import StatusBar
from nova.ui.theme import theme
from nova.ui.widgets import (
    CircularProgress,
    GlassCard,
    NeonButton,
    ParticleBackground,
    WaveformVisualizer,
    effects_enabled,
)

# Teinte d'accent par application (repli sur un cycle pour les apps inconnues)
ACCENT_BY_APP = {
    "assistant": "primary",
    "maps": "secondary",
    "calendar": "accent",
    "sensors": "success",
    "radio": "warning",
    "settings": "text_secondary",
}
ACCENT_CYCLE = ("primary", "secondary", "accent", "success", "warning")

MONTHS_FR = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
             "aout", "septembre", "octobre", "novembre", "decembre")
DAYS_FR = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")


class HomeScreen(Screen):
    """Accueil : statut, carte horloge, carte agenda, grille, onde IA."""

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "home")
        super(HomeScreen, self).__init__(**kwargs)
        self.launcher = None
        self._clocks = []
        self.build_ui()

        self._clocks.append(Clock.schedule_interval(self.update_time, 1))
        self._clocks.append(Clock.schedule_interval(self.update_battery, 30))
        self._clocks.append(Clock.schedule_interval(self.update_next_event, 60))

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def build_ui(self):
        root = FloatLayout()

        self.particles = ParticleBackground(size_hint=(1, 1))
        root.add_widget(self.particles)

        self.status = StatusBar(size_hint=(1, None), pos_hint={"top": 1})
        root.add_widget(self.status)

        root.add_widget(self._build_clock_card())
        root.add_widget(self._build_event_card())

        self.apps_grid = GridLayout(
            cols=3, spacing=dp(12), padding=[dp(4), dp(4)],
            size_hint=(0.94, None), height=dp(170),
            pos_hint={"center_x": 0.5, "top": 0.50},
        )
        root.add_widget(self.apps_grid)

        self.waveform = WaveformVisualizer(
            size_hint=(0.32, None), height=dp(22), amplitude=0.35, active=False,
            pos_hint={"center_x": 0.5, "y": 0.055},
        )
        root.add_widget(self.waveform)

        self.ai_label = Label(
            text="NOVA en veille", font_size=dp(11),
            color=theme.get_rgba("text_secondary", 0.75),
            size_hint=(0.6, None), height=dp(16),
            pos_hint={"center_x": 0.5, "y": 0.005},
        )
        root.add_widget(self.ai_label)

        self.add_widget(root)
        self.update_time()

    def _build_clock_card(self):
        card = GlassCard(
            size_hint=(0.92, None), height=dp(104), animate_on_touch=False,
            pos_hint={"center_x": 0.5, "top": 0.895},
        )

        self.time_label = Label(
            text="--:--", font_size=dp(42), bold=True, halign="left", valign="middle",
            color=theme.get_rgba("text_primary"),
            size_hint=(0.42, 0.5), pos_hint={"x": 0.05, "center_y": 0.62},
        )
        self.time_label.bind(size=self._align_left)
        card.add_widget(self.time_label)

        self.date_label = Label(
            text="", font_size=dp(12), halign="left", valign="middle",
            color=theme.get_rgba("text_secondary"),
            size_hint=(0.55, 0.3), pos_hint={"x": 0.05, "center_y": 0.24},
        )
        self.date_label.bind(size=self._align_left)
        card.add_widget(self.date_label)

        self.greeting_label = Label(
            text="Bonjour", font_size=dp(18), halign="right", valign="middle",
            color=theme.get_rgba("text_secondary"),
            size_hint=(0.32, 0.4), pos_hint={"right": 0.80, "center_y": 0.5},
        )
        self.greeting_label.bind(size=self._align_left)
        card.add_widget(self.greeting_label)

        self.battery_ring = CircularProgress(
            size_hint=(None, None), size=(dp(58), dp(58)),
            pos_hint={"right": 0.965, "center_y": 0.5},
        )
        card.add_widget(self.battery_ring)

        return card

    def _build_event_card(self):
        card = GlassCard(
            size_hint=(0.92, None), height=dp(64), animate_on_touch=False,
            pos_hint={"center_x": 0.5, "top": 0.655},
        )

        caption = Label(
            text="PROCHAIN EVENEMENT", font_size=dp(9.5), halign="left", valign="middle",
            color=theme.get_rgba("text_secondary", 0.85),
            size_hint=(0.6, 0.35), pos_hint={"x": 0.05, "top": 0.92},
        )
        caption.bind(size=self._align_left)
        card.add_widget(caption)

        self.event_label = Label(
            text="Aucun evenement prevu", font_size=dp(15), halign="left", valign="middle",
            color=theme.get_rgba("text_primary"),
            size_hint=(0.62, 0.45), pos_hint={"x": 0.05, "y": 0.12},
        )
        self.event_label.bind(size=self._align_left)
        card.add_widget(self.event_label)

        self.countdown_label = Label(
            text="", font_size=dp(13), halign="right", valign="middle",
            color=theme.get_rgba("accent"),
            size_hint=(0.26, 0.6), pos_hint={"right": 0.95, "center_y": 0.5},
        )
        self.countdown_label.bind(size=self._align_left)
        card.add_widget(self.countdown_label)

        return card

    @staticmethod
    def _align_left(widget, size):
        widget.text_size = size

    # ------------------------------------------------------------------
    # Liaison avec le launcher
    # ------------------------------------------------------------------
    def bind_launcher(self, launcher):
        """Remplit la grille avec les applications chargées."""
        self.launcher = launcher
        self.populate_apps(launcher.get_app_info())

    def populate_apps(self, apps_info):
        self.apps_grid.clear_widgets()
        apps = list(apps_info or [])

        if not apps:
            self.apps_grid.add_widget(Label(
                text="Aucune application detectee",
                color=theme.get_rgba("text_secondary"),
            ))
            return

        rows = int(math.ceil(len(apps) / float(self.apps_grid.cols)))
        self.apps_grid.height = rows * dp(78) + (rows - 1) * dp(12) + dp(8)

        for index, app in enumerate(apps):
            tile = NeonButton(
                icon=app.get("icon", ""),
                text=app.get("name", app["id"]),
                accent=ACCENT_BY_APP.get(app["id"], ACCENT_CYCLE[index % len(ACCENT_CYCLE)]),
            )
            tile.bind(on_release=lambda _w, app_id=app["id"]: self.launch_app(app_id))
            self.apps_grid.add_widget(tile)

    def launch_app(self, app_id):
        if self.launcher is not None:
            self.launcher.launch_app(app_id)

    # ------------------------------------------------------------------
    # Mises à jour
    # ------------------------------------------------------------------
    def update_time(self, _dt=None):
        now = datetime.now()
        self.time_label.text = now.strftime("%H:%M")
        self.date_label.text = "{} {} {}".format(
            DAYS_FR[now.weekday()], now.day, MONTHS_FR[now.month - 1])
        self.greeting_label.text = self.greeting_text(now.hour)

    @staticmethod
    def greeting_text(hour):
        if hour < 5:
            return "Bonne nuit"
        if hour < 12:
            return "Bonjour"
        if hour < 18:
            return "Bon apres-midi"
        if hour < 22:
            return "Bonsoir"
        return "Bonne nuit"

    def update_battery(self, _dt=None):
        try:
            from nova.power_manager import get_power_manager
            level = get_power_manager().get_battery_level()
        except Exception:
            return
        self.battery_ring.set_value(level)
        if level < 20:
            key = "error"
        elif level < 40:
            key = "warning"
        else:
            key = "primary"
        self.battery_ring.ring_color = list(theme.get_rgba(key))

    def update_next_event(self, _dt=None):
        try:
            from apps.calendar import storage
            events = storage.get_today_events()
        except Exception:
            return

        now = datetime.now()
        current = now.strftime("%H:%M")
        for event in events:
            if event["event_time"] >= current:
                self.event_label.text = event["title"]
                self.countdown_label.text = self._countdown(now, event["event_time"])
                return

        self.event_label.text = "Aucun evenement prevu"
        self.countdown_label.text = ""

    @staticmethod
    def _countdown(now, event_time):
        try:
            hours, minutes = (int(part) for part in event_time.split(":")[:2])
        except (ValueError, TypeError):
            return ""
        delta = (hours * 60 + minutes) - (now.hour * 60 + now.minute)
        if delta <= 0:
            return "maintenant"
        if delta < 60:
            return "dans {} min".format(delta)
        return "dans {}h{:02d}".format(delta // 60, delta % 60)

    def set_next_event(self, text):
        """Conservé pour compatibilité avec l'ancienne API."""
        self.event_label.text = text or "Aucun evenement prevu"

    # ------------------------------------------------------------------
    # Assistant vocal
    # ------------------------------------------------------------------
    def set_ai_active(self, active, message=None):
        """Bascule l'onde entre veille et écoute."""
        self.waveform.active = bool(active)
        if message is not None:
            self.ai_label.text = message
        else:
            self.ai_label.text = "NOVA ecoute..." if active else "NOVA en veille"

    # ------------------------------------------------------------------
    # Cycle de vie de l'écran
    # ------------------------------------------------------------------
    def on_pre_enter(self, *_args):
        self.update_time()
        self.update_battery()
        self.update_next_event()
        self.opacity = 0 if effects_enabled("animations") else 1

    def on_enter(self, *_args):
        if effects_enabled("animations"):
            Animation.cancel_all(self, "opacity")
            Animation(opacity=1, duration=0.25, t="out_quad").start(self)

    def on_cleanup(self):
        for clock in self._clocks:
            clock.cancel()
        self._clocks = []
        self.particles.stop()
        self.waveform.stop()
        self.status.stop()
