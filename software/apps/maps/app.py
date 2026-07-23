#!/usr/bin/env python3
"""Application Maps — position et vitesse GPS (module NEO-6M via gpsd)."""

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager

try:
    import gpsd
except ImportError:
    gpsd = None


class MapsApp(BaseApp):
    app_name = "Maps"
    app_icon = "🗺"
    app_id = "maps"

    def __init__(self, **kwargs):
        self.position = {"lat": None, "lon": None, "speed": 0.0, "sats": 0}
        self.connected = False
        super().__init__(**kwargs)
        self._clock = Clock.schedule_interval(self.update_gps, 2)

    def build_ui(self):
        super().build_ui()

        self.gps_info = Label(
            text="Acquisition GPS...", font_size=18, halign="center", valign="middle",
            color=theme_manager.get_color("text"),
        )
        self.gps_info.bind(size=lambda w, _v: setattr(w, "text_size", w.size))
        self.content.add_widget(self.gps_info)

        modes = BoxLayout(size_hint_y=0.16, spacing=8)
        for label in ("Normal", "Minimaliste"):
            button = Button(text=label, font_size=15, background_normal="",
                            background_color=theme_manager.get_color("surface"))
            button.bind(on_press=lambda _w, m=label: self.set_mode(m))
            modes.add_widget(button)
        self.content.add_widget(modes)

        self.mode = "Normal"

    def set_mode(self, mode):
        self.mode = mode
        self.render()

    def connect_gps(self):
        if gpsd is None or self.connected:
            return self.connected
        try:
            gpsd.connect()
            self.connected = True
        except Exception as error:
            print("[maps] gpsd indisponible : {}".format(error))
            self.connected = False
        return self.connected

    def update_gps(self, dt=None):
        if not self.connect_gps():
            self.render()
            return
        try:
            packet = gpsd.get_current()
            if packet.mode >= 2:
                self.position["lat"] = packet.lat
                self.position["lon"] = packet.lon
                self.position["speed"] = packet.hspeed * 3.6
                self.position["sats"] = packet.sats
        except Exception as error:
            print("[maps] lecture GPS : {}".format(error))
        self.render()

    def render(self):
        if gpsd is None:
            self.gps_info.text = (
                "Module gpsd-py3 non installe.\n\n"
                "sudo apt install gpsd gpsd-clients\n"
                "pip install gpsd-py3"
            )
            return
        if not self.connected:
            self.gps_info.text = (
                "En attente du demon gpsd.\n\n"
                "Branchez le NEO-6M puis :\n"
                "sudo systemctl start gpsd"
            )
            return
        if self.position["lat"] is None:
            self.gps_info.text = "Acquisition des satellites...\nSatellites : {}".format(
                self.position["sats"])
            return

        if self.mode == "Minimaliste":
            self.gps_info.text = "{:.0f} km/h".format(self.position["speed"])
        else:
            self.gps_info.text = (
                "Latitude  : {:.6f}\n"
                "Longitude : {:.6f}\n"
                "Vitesse   : {:.1f} km/h\n"
                "Satellites: {}"
            ).format(self.position["lat"], self.position["lon"],
                     self.position["speed"], self.position["sats"])

    def on_cleanup(self):
        if getattr(self, "_clock", None) is not None:
            self._clock.cancel()


NovaApp = MapsApp
