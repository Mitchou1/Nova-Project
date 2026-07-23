#!/usr/bin/env python3
"""Application Réglages."""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider

from apps.base_app import BaseApp
from nova import __version__
from nova.ui.theme import THEME_LABELS, theme_manager
from nova.utils.config_loader import get_config
from nova.utils.platform_utils import is_raspberry_pi


class SettingsApp(BaseApp):
    app_name = "Reglages"
    app_icon = "⚙"
    app_id = "settings"

    def build_ui(self):
        super().build_ui()
        config = get_config()
        audio = config.get("audio", {})

        self.content.add_widget(self._slider_row(
            "Luminosite", 10, 100, audio.get("brightness", 80), self.on_brightness))
        self.content.add_widget(self._slider_row(
            "Volume", 0, 100, audio.get("volume", 70), self.on_volume))

        theme_row = BoxLayout(size_hint_y=0.18, spacing=8)
        theme_row.add_widget(Label(text="Theme", size_hint_x=0.3, font_size=16))
        for label, key in THEME_LABELS.items():
            button = Button(text=label, font_size=15, background_normal="",
                            background_color=theme_manager.get_color("surface"))
            button.bind(on_press=lambda _w, k=key: self.change_theme(k))
            theme_row.add_widget(button)
        self.content.add_widget(theme_row)

        self.info = Label(
            text=self._info_text(), font_size=13, size_hint_y=0.30,
            color=theme_manager.get_color("text_secondary"),
        )
        self.content.add_widget(self.info)

    def _slider_row(self, label, minimum, maximum, value, callback):
        row = BoxLayout(size_hint_y=0.18, spacing=8)
        row.add_widget(Label(text=label, size_hint_x=0.3, font_size=16))
        slider = Slider(min=minimum, max=maximum, value=value)
        slider.bind(value=callback)
        row.add_widget(slider)
        self.value_labels = getattr(self, "value_labels", {})
        value_label = Label(text="{:.0f}".format(value), size_hint_x=0.15, font_size=15)
        self.value_labels[label] = value_label
        row.add_widget(value_label)
        return row

    def on_brightness(self, _slider, value):
        self.value_labels["Luminosite"].text = "{:.0f}".format(value)
        self._save_audio("brightness", int(value))

    def on_volume(self, _slider, value):
        self.value_labels["Volume"].text = "{:.0f}".format(value)
        self._save_audio("volume", int(value))

    def _save_audio(self, key, value):
        config = get_config()
        audio = dict(config.get("audio", {}))
        audio[key] = value
        config.set("audio", audio)

    def change_theme(self, theme_key):
        if theme_manager.set_theme(theme_key):
            get_config().set("theme", theme_key)
            self.info.text = self._info_text()
            print("[settings] theme applique : {} (redemarrage conseille)".format(theme_key))

    def _info_text(self):
        platform = "Raspberry Pi" if is_raspberry_pi() else "PC (simulation)"
        return "NOVA v{}\n{}\nTheme : {}".format(
            __version__, platform, theme_manager.current_theme)


NovaApp = SettingsApp
