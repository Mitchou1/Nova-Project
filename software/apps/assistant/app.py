#!/usr/bin/env python3
"""Application Assistant IA — enregistrement micro puis pipeline local."""

import os
import subprocess
import tempfile
import threading

from kivy.clock import Clock
from kivy.uix.button import Button
from kivy.uix.label import Label

from apps.base_app import BaseApp
from nova.ai_engine import get_ai
from nova.ui.theme import theme_manager
from nova.utils.platform_utils import has_command

AUDIO_PATH = os.path.join(tempfile.gettempdir(), "nova_input.wav")


class AssistantApp(BaseApp):
    app_name = "Assistant IA"
    app_icon = "🤖"
    app_id = "assistant"

    def __init__(self, **kwargs):
        self.is_listening = False
        self.recorder = None
        super().__init__(**kwargs)

    def build_ui(self):
        super().build_ui()

        self.chat_label = Label(
            text=self.welcome_text(), font_size=16, halign="center", valign="middle",
            color=theme_manager.get_color("text"),
        )
        self.chat_label.bind(size=lambda w, _v: setattr(w, "text_size", w.size))
        self.content.add_widget(self.chat_label)

        self.mic_button = Button(
            text="Parler", font_size=22, size_hint_y=0.26, background_normal="",
            background_color=theme_manager.get_color("primary"),
        )
        self.mic_button.bind(on_press=self.toggle_listen)
        self.content.add_widget(self.mic_button)

    def welcome_text(self):
        missing = get_ai().missing_parts()
        if missing:
            return ("Bonjour, je suis NOVA.\n\n"
                    "Modules manquants : {}\n"
                    "Lancez scripts/setup_ai.sh").format(", ".join(missing))
        return "Bonjour, je suis NOVA.\nAppuyez sur Parler."

    def toggle_listen(self, *_):
        if self.is_listening:
            self.stop_and_process()
        else:
            self.start_recording()

    def start_recording(self):
        if not has_command("arecord"):
            self.chat_label.text = ("Micro indisponible.\n\n"
                                    "sudo apt install alsa-utils")
            return
        try:
            self.recorder = subprocess.Popen(
                ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", AUDIO_PATH]
            )
        except OSError as error:
            self.chat_label.text = "Erreur micro : {}".format(error)
            return

        self.is_listening = True
        self.mic_button.text = "Stop"
        self.mic_button.background_color = theme_manager.get_color("error")
        self.chat_label.text = "J'ecoute..."

    def stop_and_process(self):
        self.is_listening = False
        self.mic_button.text = "Parler"
        self.mic_button.background_color = theme_manager.get_color("primary")
        self.chat_label.text = "Traitement en cours..."

        if self.recorder is not None:
            self.recorder.terminate()
            self.recorder.wait(timeout=5)
            self.recorder = None

        threading.Thread(target=self._process_worker, daemon=True).start()

    def _process_worker(self):
        try:
            result = get_ai().process_audio(AUDIO_PATH)
            text = result.get("text", "")
            response = result.get("response", "")
            if result.get("action") == "calendar":
                message = "Commande agenda detectee :\n{}".format(text)
            elif result.get("action") == "settings":
                message = "Commande reglages detectee :\n{}".format(text)
            else:
                message = "Vous : {}\n\nNOVA : {}".format(text, response)
        except Exception as error:
            message = "Erreur : {}".format(error)

        Clock.schedule_once(lambda dt: setattr(self.chat_label, "text", message), 0)

    def on_cleanup(self):
        if self.recorder is not None:
            self.recorder.terminate()


NovaApp = AssistantApp
