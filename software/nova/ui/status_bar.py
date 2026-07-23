#!/usr/bin/env python3
"""Barre de statut NOVA : heure, réseau, Bluetooth, batterie.

Les indicateurs lisent de vraies valeurs système quand elles sont
disponibles, et retombent silencieusement en mode inconnu sinon.
"""

import glob
import os
from datetime import datetime

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from nova.ui.theme import theme


# ---------------------------------------------------------------------------
# Lecture système
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------
class StatusDot(BoxLayout):
    """Pastille colorée + libellé : lisible sans police emoji."""

    def __init__(self, caption, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(5))
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("width", dp(56))
        super(StatusDot, self).__init__(**kwargs)

        self.dot = Widget(size_hint=(None, None), size=(dp(7), dp(7)))
        with self.dot.canvas:
            self.dot_color = Color(*theme.get_rgba("text_secondary"))
            self.dot_shape = Rectangle(size=self.dot.size)
        self.dot.bind(pos=self._place_dot, size=self._place_dot)

        holder = BoxLayout(size_hint_x=None, width=dp(12))
        holder.add_widget(self.dot)
        self.add_widget(holder)

        self.caption = Label(
            text=caption, font_size=dp(11), halign="left", valign="middle",
            color=theme.get_rgba("text_secondary"),
        )
        self.caption.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self.caption)

    def _place_dot(self, *_args):
        self.dot_shape.pos = (self.dot.x, self.dot.center_y - dp(3.5))
        self.dot_shape.size = (dp(7), dp(7))

    def set_state(self, state):
        colors = {"up": "success", "down": "error", "none": "text_secondary"}
        self.dot_color.rgba = theme.get_rgba(colors.get(state, "text_secondary"))


class BatteryGauge(BoxLayout):
    """Jauge dessinée : aucune dépendance à une police d'icônes."""

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("width", dp(76))
        super(BatteryGauge, self).__init__(**kwargs)

        self.level = 0.0

        self.value_label = Label(
            text="--%", font_size=dp(12), halign="right", valign="middle",
            color=theme.get_rgba("text_primary"), size_hint_x=None, width=dp(38),
        )
        self.value_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self.value_label)

        self.gauge = Widget(size_hint=(None, 1), width=dp(30))
        with self.gauge.canvas:
            self.shell_color = Color(*theme.get_rgba("text_secondary", 0.55))
            self.shell = Rectangle()
            self.cap = Rectangle()
            self.fill_color = Color(*theme.get_rgba("success"))
            self.fill = Rectangle()
            self.hollow_color = Color(*theme.get_rgba("background"))
            self.hollow = Rectangle()
        self.gauge.bind(pos=self._redraw, size=self._redraw)
        self.add_widget(self.gauge)

    def _redraw(self, *_args):
        width, height = dp(24), dp(12)
        x = self.gauge.x
        y = self.gauge.center_y - height / 2.0

        self.shell.pos = (x, y)
        self.shell.size = (width, height)
        self.cap.pos = (x + width, y + height * 0.28)
        self.cap.size = (dp(2.5), height * 0.44)

        border = dp(1.5)
        self.hollow.pos = (x + border, y + border)
        self.hollow.size = (width - border * 2, height - border * 2)

        usable = (width - border * 2) * max(0.0, min(1.0, self.level / 100.0))
        self.fill.pos = (x + border, y + border)
        self.fill.size = (usable, height - border * 2)

    def set_level(self, level):
        self.level = float(level)
        self.value_label.text = "{:.0f}%".format(self.level)
        if self.level < 20:
            key = "error"
        elif self.level < 40:
            key = "warning"
        else:
            key = "success"
        self.fill_color.rgba = theme.get_rgba(key)
        self._redraw()


class StatusBar(BoxLayout):
    """Bandeau supérieur, style montre connectée."""

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(34))
        kwargs.setdefault("padding", [dp(14), 0, dp(14), 0])
        kwargs.setdefault("spacing", dp(8))
        super(StatusBar, self).__init__(**kwargs)

        with self.canvas.before:
            self.bg_color = Color(*theme.get_rgba("surface", 0.75))
            self.bg = Rectangle()
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        self.wifi = StatusDot("WI-FI")
        self.bluetooth = StatusDot("BT", width=dp(38))
        self.add_widget(self.wifi)
        self.add_widget(self.bluetooth)

        self.add_widget(Widget())

        self.time_label = Label(
            text="--:--", font_size=dp(15), bold=True,
            color=theme.get_rgba("text_primary"),
            size_hint_x=None, width=dp(58),
        )
        self.add_widget(self.time_label)

        self.add_widget(Widget())

        self.battery = BatteryGauge()
        self.add_widget(self.battery)

        self.update_time()
        self.update_status()
        self._time_clock = Clock.schedule_interval(self.update_time, 1)
        self._status_clock = Clock.schedule_interval(self.update_status, 10)

    def _redraw_bg(self, *_args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def update_time(self, _dt=None):
        self.time_label.text = datetime.now().strftime("%H:%M")

    def update_status(self, _dt=None):
        self.wifi.set_state(wifi_state())
        self.bluetooth.set_state(bluetooth_state())
        try:
            from nova.power_manager import get_power_manager
            self.battery.set_level(get_power_manager().get_battery_level())
        except Exception:
            pass

    def stop(self):
        for clock in (getattr(self, "_time_clock", None),
                      getattr(self, "_status_clock", None)):
            if clock is not None:
                clock.cancel()
