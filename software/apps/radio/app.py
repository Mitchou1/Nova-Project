#!/usr/bin/env python3
"""Application Radio — scan de fréquences via RTL-SDR."""

import subprocess
import threading

from kivy.clock import Clock
from kivy.uix.button import Button
from kivy.uix.label import Label

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager
from nova.utils.platform_utils import has_command


class RadioApp(BaseApp):
    app_name = "Radio"
    app_icon = "📻"
    app_id = "radio"

    def __init__(self, **kwargs):
        self.scanning = False
        super().__init__(**kwargs)

    def build_ui(self):
        super().build_ui()

        self.status_label = Label(
            text=self.idle_text(), font_size=16, halign="center", valign="middle",
            color=theme_manager.get_color("text"),
        )
        self.status_label.bind(size=lambda w, _v: setattr(w, "text_size", w.size))
        self.content.add_widget(self.status_label)

        self.scan_button = Button(
            text="Demarrer le scan", size_hint_y=0.18, font_size=17,
            background_normal="", background_color=theme_manager.get_color("success"),
        )
        self.scan_button.bind(on_press=self.toggle_scan)
        self.content.add_widget(self.scan_button)

    def idle_text(self):
        if not has_command("rtl_test"):
            return ("Scanner RTL-SDR\n\nOutils absents.\n"
                    "sudo apt install rtl-sdr")
        return "Scanner RTL-SDR\n\nEtat : inactif\nDongle detecte"

    def toggle_scan(self, *_):
        if self.scanning:
            self.scanning = False
            self.scan_button.text = "Demarrer le scan"
            self.status_label.text = self.idle_text()
            return
        if not has_command("rtl_power"):
            self.status_label.text = ("Outils RTL-SDR absents.\n\n"
                                      "sudo apt install rtl-sdr")
            return
        self.scanning = True
        self.scan_button.text = "Arreter le scan"
        self.status_label.text = "Scan en cours (88-108 MHz)..."
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            result = subprocess.run(
                ["rtl_power", "-f", "88M:108M:100k", "-i", "5", "-1", "-"],
                capture_output=True, text=True, timeout=60, check=False,
            )
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            summary = "Scan termine\n{} lignes de mesure".format(len(lines))
        except (subprocess.SubprocessError, OSError) as error:
            summary = "Erreur de scan :\n{}".format(error)

        def finish(dt):
            self.scanning = False
            self.scan_button.text = "Demarrer le scan"
            self.status_label.text = summary

        Clock.schedule_once(finish, 0)


NovaApp = RadioApp
