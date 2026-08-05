#!/usr/bin/env python3
"""
App Radio NOVA — Détection RF avec RTL-SDR (mock/simulation)
Interface prête, attente matériel
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle
import random
import math

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager
from nova.ui.widgets import GlassCard, NeonButton


class SpectrumBar(Label):
    """Barre du spectre fréquentiel."""

    def __init__(self, freq_mhz, **kwargs):
        super().__init__(**kwargs)
        self.freq_mhz = freq_mhz
        self.amplitude = 0
        self._setup_graphics()

    def _setup_graphics(self):
        with self.canvas:
            self.bar_color = Color(*theme_manager.get_color("primary"))
            self.bar = Rectangle(pos=self.pos, size=(self.width, dp(2)))
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.bar.pos = self.pos
        self.bar.size = (self.width, max(dp(2), self.height * self.amplitude))

    def set_amplitude(self, val):
        self.amplitude = max(0, min(val, 1))
        self._update()


class RadioApp(BaseApp):
    """Application Radio / RTL-SDR — simulation."""

    app_name = "Radio"
    app_icon = "radio"
    app_id = "radio"

    def __init__(self, **kwargs):
        self.frequency = 446.0  # MHz
        self.scanning = False
        self.signals_detected = []
        super().__init__(**kwargs)

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ─── INDICATEUR SIMULATION ─────────────────────────────────
        sim_card = GlassCard(
            size_hint=(0.95, None),
            height=dp(40),
            pos_hint={'center_x': 0.5, 'top': 0.92},
            corner_radius=dp(2)
        )
        sim_card.add_widget(Label(
            text="Mode simulation — RTL-SDR non connecte",
            font_size=dp(11),
            color=theme_manager.get_color("warning"),
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        ))
        main.add_widget(sim_card)

        # ─── AFFICHAGE FRÉQUENCE ───────────────────────────────────
        from nova import fonts as _f

        freq_card = GlassCard(
            size_hint=(0.95, None),
            height=dp(104),
            pos_hint={'center_x': 0.5, 'top': 0.86},
            corner_radius=dp(2),
            chamfer=dp(8),
        )

        # Libellé en label-caps au-dessus du nombre (charte)
        freq_card.add_widget(Label(
            text=" ".join("FREQUENCE"),
            font_name=_f.FONT_MONO, font_size=dp(8),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'center_x': 0.5, 'top': 0.97},
            size_hint=(0.9, 0.18),
        ))

        # Nombre héro — data-mono (charte : les données techniques en mono)
        self.freq_label = Label(
            text="{:.3f} MHz".format(self.frequency),
            font_name=_f.FONT_MONO, font_size=dp(30), bold=True,
            color=theme_manager.get_color("primary"),
            pos_hint={'center_x': 0.5, 'top': 0.78},
            size_hint=(0.9, 0.42),
        )
        freq_card.add_widget(self.freq_label)

        # Rangée de statistiques (modèle de la maquette : libellé + valeur)
        stats = [
            ("PUISSANCE", "signal_label_power", "-- dBm"),
            ("ETAT", "signal_label", "AUCUN SIGNAL"),
            ("PROXIMITE", "band_label", "--"),
        ]
        for i, (libelle, attr, defaut) in enumerate(stats):
            cx = (i + 0.5) / 3.0
            freq_card.add_widget(Label(
                text=libelle,
                font_name=_f.FONT_MONO, font_size=dp(7),
                color=theme_manager.get_color("text_secondary"),
                pos_hint={'center_x': cx, 'top': 0.34},
                size_hint=(0.33, 0.14),
            ))
            lab = Label(
                text=defaut,
                font_name=_f.FONT_MONO, font_size=dp(11),
                color=theme_manager.get_color("text"),
                pos_hint={'center_x': cx, 'top': 0.20},
                size_hint=(0.33, 0.18),
            )
            setattr(self, attr, lab)
            freq_card.add_widget(lab)

        main.add_widget(freq_card)

        # ─── SPECTRE SIMULÉ ──────────────────────────────────────
        spectrum_card = GlassCard(
            size_hint=(0.95, None),
            height=dp(150),
            pos_hint={'center_x': 0.5, 'top': 0.62},
            corner_radius=dp(2)
        )

        self.spectrum_bars = []
        bar_count = 32
        for i in range(bar_count):
            bar = SpectrumBar(
                freq_mhz=self.frequency - 2 + (i * 4 / bar_count),
                size_hint=(None, 1),
                width=dp(8),
                pos_hint={'x': 0.05 + (i / bar_count) * 0.9, 'y': 0.1}
            )
            self.spectrum_bars.append(bar)
            spectrum_card.add_widget(bar)

        main.add_widget(spectrum_card)

        # ─── CONTRÔLES ────────────────────────────────────────────
        controls = BoxLayout(
            size_hint=(0.95, None),
            height=dp(50),
            pos_hint={'center_x': 0.5, 'top': 0.38},
            spacing=dp(10)
        )

        btn_scan = NeonButton(
            icon="search", text="Scanner",
            size_hint=(1, 1),
            corner_radius=dp(2)
        )
        btn_scan.bind(on_press=self._toggle_scan)
        controls.add_widget(btn_scan)

        btn_minus = NeonButton(
            icon="chevron_left", text="-1MHz",
            size_hint=(1, 1),
            corner_radius=dp(2)
        )
        btn_minus.bind(on_press=lambda x: self._change_freq(-1))
        controls.add_widget(btn_minus)

        btn_plus = NeonButton(
            icon="chevron_right", text="+1MHz",
            size_hint=(1, 1),
            corner_radius=dp(2)
        )
        btn_plus.bind(on_press=lambda x: self._change_freq(1))
        controls.add_widget(btn_plus)

        main.add_widget(controls)

        # ─── HISTORIQUE SIGNAUX ───────────────────────────────────
        history_card = GlassCard(
            size_hint=(0.95, None),
            height=dp(120),
            pos_hint={'center_x': 0.5, 'top': 0.28},
            corner_radius=dp(2)
        )

        history_card.add_widget(Label(
            text="Historique signaux",
            font_size=dp(13),
            bold=True,
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'x': 0.05, 'top': 0.9},
            size_hint=(0.9, 0.2),
            halign='left'
        ))

        self.history_label = Label(
            text="Aucun signal enregistré",
            font_size=dp(11),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'x': 0.05, 'y': 0.1},
            size_hint=(0.9, 0.6),
            halign='left',
            valign='top'
        )
        history_card.add_widget(self.history_label)

        main.add_widget(history_card)

        # Le timer du spectre est demarre a l'entree de l'ecran (on_enter)
        self._spectrum_clock = None

    def on_enter(self, *args):
        """Demarre l'animation quand l'ecran devient visible."""
        if getattr(self, "_spectrum_clock", None) is None:
            self._spectrum_clock = Clock.schedule_interval(self._animate_spectrum, 0.1)

    def on_leave(self, *args):
        """Arrete l'animation quand on quitte l'ecran (evite l'accumulation)."""
        if getattr(self, "_spectrum_clock", None) is not None:
            self._spectrum_clock.cancel()
            self._spectrum_clock = None

    def _animate_spectrum(self, dt):
        """Anime le spectre simulé."""
        t = Clock.get_time()
        for i, bar in enumerate(self.spectrum_bars):
            # Bruit de fond
            noise = random.random() * 0.15

            # Pic simulé aléatoire
            peak = 0
            if self.scanning and random.random() > 0.97:
                peak = random.random() * 0.8

            # Forme d'onde
            wave = abs(math.sin(t * 2 + i * 0.3)) * 0.1

            bar.set_amplitude(noise + wave + peak)

    def _toggle_scan(self, instance):
        """Active/désactive le scan."""
        self.scanning = not self.scanning

        if self.scanning:
            instance.text = "ARRETER"
            self.signal_label.text = "SCAN..."
            self.signal_label.color = theme_manager.get_color("primary")
            self.signal_label_power.text = "-- dBm"

            # Simuler détection
            Clock.schedule_once(self._simulate_detection, 3)
        else:
            instance.text = "SCANNER"
            self.signal_label.text = "AUCUN SIGNAL"
            self.signal_label.color = theme_manager.get_color("text_secondary")
            self.signal_label_power.text = "-- dBm"

    def _simulate_detection(self, dt):
        """Simule la détection d'un signal."""
        if not self.scanning:
            return

        freq = self.frequency + random.uniform(-1, 1)
        power = random.uniform(-80, -30)

        signal_info = f"{freq:.3f} MHz | {power:.0f} dBm"
        self.signals_detected.append(signal_info)

        # Charte : la puissance a sa propre colonne, l'etat reste court
        self.signal_label.text = "DETECTE"
        self.signal_label.color = theme_manager.get_color("warning")
        self.signal_label_power.text = f"{power:.0f} dBm"
        # Cahier des charges : indicateur de proximite selon la puissance.
        # Plus le signal est fort (dBm proche de 0), plus la source est proche.
        if power > -45:
            proximite, couleur = "PROCHE", "error"
        elif power > -65:
            proximite, couleur = "MOYEN", "warning"
        else:
            proximite, couleur = "LOINTAIN", "text_secondary"
        self.signal_label_power.color = theme_manager.get_color(couleur)
        self.band_label.text = proximite

        # Mettre à jour historique
        history_text = "\n".join(self.signals_detected[-5:])
        self.history_label.text = history_text

        print(f"[radio] Signal : {signal_info}")

    def _change_freq(self, delta):
        """Change la fréquence."""
        self.frequency += delta
        self.freq_label.text = f"{self.frequency:.3f} MHz"
        # La bande depend de la frequence (VHF sous 300 MHz, UHF au-dessus)
        self.band_label.text = "--"


NovaApp = RadioApp
