#!/usr/bin/env python3
"""Barre de statut : heure, date, batterie, connectivité."""

from datetime import datetime

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from nova.ui.theme import theme_manager


class StatusBar(BoxLayout):
    """Bandeau supérieur de l'écran d'accueil."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", 0.08)
        kwargs.setdefault("padding", [10, 2])
        super().__init__(**kwargs)

        self.time_label = Label(text="--:--", font_size=18, bold=True, size_hint_x=0.25)
        self.date_label = Label(
            text="", font_size=13, size_hint_x=0.45,
            color=theme_manager.get_color("text_secondary"),
        )
        self.battery_label = Label(text="BAT --%", font_size=14, size_hint_x=0.30)

        for widget in (self.time_label, self.date_label, self.battery_label):
            self.add_widget(widget)

        self.update_time()
        self.update_battery()
        Clock.schedule_interval(self.update_time, 1)
        Clock.schedule_interval(self.update_battery, 30)

    def update_time(self, dt=None):
        now = datetime.now()
        self.time_label.text = now.strftime("%H:%M")
        self.date_label.text = now.strftime("%d/%m/%Y")

    def update_battery(self, dt=None):
        try:
            from nova.power_manager import get_power_manager
            level = get_power_manager().get_battery_level()
        except Exception:
            self.battery_label.text = "BAT --%"
            return

        self.battery_label.text = "BAT {:.0f}%".format(level)
        if level < 20:
            self.battery_label.color = theme_manager.get_color("error")
        elif level < 40:
            self.battery_label.color = theme_manager.get_color("warning")
        else:
            self.battery_label.color = theme_manager.get_color("text")
