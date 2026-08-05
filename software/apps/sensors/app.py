#!/usr/bin/env python3
"""
App Capteurs NOVA — Dashboard avec simulation
Affiche données MPU6050, BME280, VL53L0X, GPS (simulation)
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import DictProperty
import math
import random

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager
from nova.ui.widgets import GlassCard, WaveformVisualizer


class SensorCard(GlassCard):
    """Carte capteur — charte NOVA (Stitch).

    Reprend la rangée de statistiques de la maquette : chaque mesure est une
    colonne avec son libellé en label-caps au-dessus et sa valeur en
    JetBrains Mono en dessous, séparées par des filets verticaux.
    """

    # Libellés lisibles + unité, par nom de mesure
    _METRIQUES = {
        "accel_x": ("ACCEL_X", "g"), "accel_y": ("ACCEL_Y", "g"),
        "accel_z": ("ACCEL_Z", "g"),
        "gyro_x": ("GYRO_X", "°/s"), "gyro_y": ("GYRO_Y", "°/s"),
        "gyro_z": ("GYRO_Z", "°/s"),
        "temperature": ("TEMP", "°C"), "humidity": ("HUM", "%"),
        "pressure": ("PRESSION", "hPa"),
        "distance": ("DISTANCE", "mm"), "status": ("ÉTAT", ""),
        "latitude": ("LAT", "°"), "longitude": ("LON", "°"),
        "altitude": ("ALT", "m"), "speed": ("VITESSE", "km/h"),
        "satellites": ("SATS", ""),
    }

    def __init__(self, title, icon, values_dict, unit="", **kwargs):
        super().__init__(
            size_hint=(1, None),
            height=dp(96),
            corner_radius=dp(2),
            chamfer=dp(8),
            **kwargs
        )
        self.values_dict = values_dict
        self._build(title, icon, values_dict)

    def _build(self, title, icon, values_dict):
        from nova import fonts as _f
        from kivy.graphics import Color, Rectangle

        # --- En-tête : pastille + nom du capteur en label-caps -----------
        self.add_widget(Label(
            text=" ".join(title.upper()),          # letter-spacing simulé
            font_name=_f.FONT_MONO, font_size=dp(10),
            color=theme_manager.get_color("primary"),
            pos_hint={'x': 0.04, 'top': 0.96},
            size_hint=(0.6, 0.24),
            halign='left', valign='middle',
        ))

        # Icône Material à droite de l'en-tête (police d'icônes, pas de tofu)
        if icon:
            self.add_widget(Label(
                text=_f.icon(icon), font_name=_f.FONT_ICON, font_size=dp(15),
                color=theme_manager.get_color("text_secondary"),
                pos_hint={'right': 0.96, 'top': 0.96},
                size_hint=(0.08, 0.24),
            ))

        # --- Corps : une colonne par mesure ------------------------------
        self.value_labels = {}
        cles = list(values_dict.keys())
        n = max(1, len(cles))
        largeur = 1.0 / n

        for i, key in enumerate(cles):
            libelle, unite = self._METRIQUES.get(
                key, (key.replace("_", " ").upper(), ""))
            cx = largeur * (i + 0.5)

            # Filet vertical de séparation (sauf avant la 1re colonne)
            if i > 0:
                sep = Widget(size_hint=(None, 0.42),
                             pos_hint={'center_x': largeur * i, 'center_y': 0.38})
                with sep.canvas:
                    Color(*theme_manager.get_with_alpha("text_secondary", 0.25))
                    r = Rectangle()
                sep.bind(pos=lambda w, _v, r=r: setattr(r, "pos", (w.x, w.y)),
                         size=lambda w, _v, r=r: setattr(r, "size", (dp(1), w.height)))
                self.add_widget(sep)

            # Libellé — label-caps (mono, petit, discret)
            self.add_widget(Label(
                text=libelle,
                font_name=_f.FONT_MONO, font_size=dp(8),
                color=theme_manager.get_color("text_secondary"),
                pos_hint={'center_x': cx, 'top': 0.62},
                size_hint=(largeur, 0.18),
            ))

            # Valeur — data-mono, mise en avant
            val_label = Label(
                text=self._format(values_dict[key], unite),
                font_name=_f.FONT_MONO, font_size=dp(15),
                color=theme_manager.get_color("text"),
                pos_hint={'center_x': cx, 'top': 0.44},
                size_hint=(largeur, 0.30),
            )
            val_label._unite = unite
            self.value_labels[key] = val_label
            self.add_widget(val_label)

    @staticmethod
    def _format(valeur, unite):
        if isinstance(valeur, float):
            texte = "{:.2f}".format(valeur).rstrip("0").rstrip(".")
        else:
            texte = str(valeur)
        return "{}{}".format(texte, unite)

    def update_values(self, new_values):
        """Met à jour les valeurs affichées."""
        for key, label in self.value_labels.items():
            if key in new_values:
                label.text = self._format(new_values[key],
                                          getattr(label, "_unite", ""))


class SensorsApp(BaseApp):
    """Application Capteurs avec simulation."""

    app_name = "Capteurs"
    app_icon = "sensors"
    app_id = "sensors"

    # Données simulées
    sensor_data = DictProperty({
        "mpu6050": {
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 1.0,
            "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0
        },
        "bme280": {
            "temperature": 24.5,
            "humidity": 55.0,
            "pressure": 1013.25
        },
        "vl53l0x": {
            "distance": 500,
            "status": "OK"
        },
        "gps": {
            "latitude": 36.8065,
            "longitude": 10.1815,
            "altitude": 15,
            "speed": 0.0,
            "satellites": 8
        }
    })

    def __init__(self, **kwargs):
        self._time_base = 0
        self._simulation_active = True
        self._sim_clock = None
        super().__init__(**kwargs)

    def on_enter(self, *args):
        """Demarre la simulation quand l'ecran devient visible."""
        if self._sim_clock is None:
            self._sim_clock = Clock.schedule_interval(self._simulate_sensors, 0.5)

    def on_leave(self, *args):
        """Arrete la simulation en quittant l'ecran (audit : tournait avant
        en continu 24h/24 depuis le demarrage, meme app fermee — decharge
        batterie inutile sur un wearable)."""
        if self._sim_clock is not None:
            self._sim_clock.cancel()
            self._sim_clock = None

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ScrollView
        scroll = ScrollView(
            size_hint=(0.95, 0.88),
            pos_hint={'center_x': 0.5, 'top': 0.9}
        )

        content = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=dp(12),
            padding=dp(10)
        )
        content.bind(minimum_height=content.setter('height'))

        # ─── INDICATEUR SIMULATION ─────────────────────────────────
        sim_indicator = GlassCard(
            size_hint=(1, None),
            height=dp(40),
            corner_radius=dp(2)
        )
        sim_indicator.add_widget(Label(
            text="Mode simulation — Aucun capteur connecte",
            font_size=dp(12),
            color=theme_manager.get_color("warning"),
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        ))
        content.add_widget(sim_indicator)

        # ─── MPU6050 (Mouvement) ────────────────────────────────────
        self.mpu_card = SensorCard(
            "MPU6050",
            "3d_rotation",
            self.sensor_data["mpu6050"],
            "g / °/s"
        )
        content.add_widget(self.mpu_card)

        # ─── BME280 (Environnement) ───────────────────────────────
        self.bme_card = SensorCard(
            "BME280",
            "thermostat",
            self.sensor_data["bme280"],
            "°C / % / hPa"
        )
        content.add_widget(self.bme_card)

        # ─── VL53L0X (Distance) ────────────────────────────────────
        self.vl53_card = SensorCard(
            "VL53L0X",
            "straighten",
            self.sensor_data["vl53l0x"],
            "mm"
        )
        content.add_widget(self.vl53_card)

        # ─── GPS ────────────────────────────────────────────────────
        self.gps_card = SensorCard(
            "NEO-6M GPS",
            "explore",
            self.sensor_data["gps"],
            "° / m / km/h"
        )
        content.add_widget(self.gps_card)

        # ─── VISUALISEUR ONDE ──────────────────────────────────────
        content.add_widget(Label(
            text="Activité capteurs",
            font_size=dp(14),
            bold=True,
            color=theme_manager.get_color("text_secondary"),
            size_hint=(1, None),
            height=dp(25)
        ))

        self.waveform = WaveformVisualizer(
            size_hint=(1, None),
            height=dp(60),
            bar_count=24,
            amplitude=0.6
        )
        content.add_widget(self.waveform)

        scroll.add_widget(content)
        main.add_widget(scroll)

    def _simulate_sensors(self, dt):
        """Simule des données réalistes de capteurs."""
        if not self._simulation_active:
            return

        t = Clock.get_time()

        # MPU6050 — mouvement naturel + bruit
        self.sensor_data["mpu6050"] = {
            "accel_x": round(0.1 * math.sin(t) + random.gauss(0, 0.02), 3),
            "accel_y": round(0.05 * math.cos(t * 0.7) + random.gauss(0, 0.02), 3),
            "accel_z": round(1.0 + 0.02 * math.sin(t * 1.3) + random.gauss(0, 0.01), 3),
            "gyro_x": round(random.gauss(0, 2), 1),
            "gyro_y": round(random.gauss(0, 2), 1),
            "gyro_z": round(random.gauss(0, 1), 1),
        }

        # BME280 — variations lentes
        self.sensor_data["bme280"] = {
            "temperature": round(24.5 + 2 * math.sin(t / 3600) + random.gauss(0, 0.1), 1),
            "humidity": round(55 + 5 * math.sin(t / 1800) + random.gauss(0, 1), 1),
            "pressure": round(1013.25 + random.gauss(0, 0.5), 2),
        }

        # VL53L0X — distance variable
        self.sensor_data["vl53l0x"] = {
            "distance": int(random.gauss(500, 50)),
            "status": "OK" if random.random() > 0.05 else "ERROR"
        }

        # GPS — déplacement lent autour de Tunis
        self.sensor_data["gps"] = {
            "latitude": round(36.8065 + 0.0001 * math.sin(t / 100), 5),
            "longitude": round(10.1815 + 0.0001 * math.cos(t / 100), 5),
            "altitude": round(15 + random.gauss(0, 2), 1),
            "speed": round(abs(5 * math.sin(t / 50)) + random.gauss(0, 0.5), 1),
            "satellites": random.randint(6, 12),
        }

        # Mettre à jour les cartes
        self.mpu_card.update_values(self.sensor_data["mpu6050"])
        self.bme_card.update_values(self.sensor_data["bme280"])
        self.vl53_card.update_values(self.sensor_data["vl53l0x"])
        self.gps_card.update_values(self.sensor_data["gps"])


NovaApp = SensorsApp
