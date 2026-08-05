#!/usr/bin/env python3
"""
App Settings NOVA — Réglages système complets
Thèmes, infos système, mock WiFi/Bluetooth
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.switch import Switch
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager
from nova.ui.widgets import GlassCard, NeonButton


class SettingsRow(GlassCard):
    """Ligne de réglage — charte NOVA (Stitch).

    Titre en Sora, sous-titre en label-caps (mono), contrôle à droite.
    """

    def __init__(self, title, subtitle="", widget=None, **kwargs):
        super().__init__(
            size_hint=(1, None),
            height=dp(60),
            corner_radius=dp(2),
            **kwargs
        )
        from nova import fonts as _f

        # Titre — Sora, en majuscules (charte : libellés « commandes »)
        self.add_widget(Label(
            text=title.upper(),
            font_name=_f.FONT_DISPLAY, font_size=dp(13), bold=True,
            color=theme_manager.get_color("text"),
            pos_hint={'x': 0.03, 'center_y': 0.66},
            size_hint=(0.6, 0.38),
            halign='left', valign='middle',
        ))

        # Sous-titre — label-caps en JetBrains Mono
        self._subtitle_label = None
        if subtitle:
            self._subtitle_label = Label(
                text=subtitle.upper(),
                font_name=_f.FONT_MONO, font_size=dp(9),
                color=theme_manager.get_color("text_secondary"),
                pos_hint={'x': 0.03, 'center_y': 0.28},
                size_hint=(0.6, 0.3),
                halign='left', valign='middle',
            )
            self.add_widget(self._subtitle_label)

        # Widget de contrôle (switch, slider, etc.)
        if widget:
            widget.pos_hint = {'right': 0.97, 'center_y': 0.5}
            widget.size_hint = (None, None)
            self.add_widget(widget)

    def set_subtitle(self, texte):
        """Met à jour le sous-titre (ex. état de connexion)."""
        if self._subtitle_label is not None:
            self._subtitle_label.text = texte.upper()


class ThemeSelector(BoxLayout):
    """Sélecteur de thème avec aperçu des couleurs."""

    def __init__(self, **kwargs):
        super().__init__(orientation='horizontal', spacing=dp(10), **kwargs)
        self._buttons = {}
        self._build_themes()

    # Noms lisibles des trois modes (la charte NOVA les nomme ainsi)
    _NOMS = {"classic": "CLASSIC", "cyberpunk": "CYBER", "undercover": "DISCRET"}

    def _build_themes(self):
        from nova import fonts as _f
        from nova.ui.theme import hex_to_rgba

        for theme_key, theme_data in theme_manager.THEMES.items():
            btn = NeonButton(
                text=self._NOMS.get(theme_key, theme_key.upper()),
                size_hint=(None, None),
                size=(dp(96), dp(50)),
                corner_radius=dp(2),
            )
            # BUG CORRIGE : chaque bouton affichait la couleur du theme ACTIF
            # (donc trois rectangles identiques). Il montre desormais SA
            # propre couleur, pour qu'on distingue les trois themes.
            couleur = hex_to_rgba(theme_data["primary"])
            btn.bg_color.rgba = (couleur[0], couleur[1], couleur[2], 0.22)
            btn.border_color.rgba = couleur
            btn.label.color = couleur
            btn.label.font_name = _f.FONT_MONO
            btn.bind(on_press=lambda x, tk=theme_key: self._select_theme(tk))
            self._buttons[theme_key] = btn
            self.add_widget(btn)
        self._mark_active()

    def _mark_active(self):
        """Souligne le thème actuellement actif (bordure épaisse)."""
        actif = theme_manager.current_theme
        for cle, btn in self._buttons.items():
            btn.border_width = 2.6 if cle == actif else 1.0
            btn._refresh()

    def _select_theme(self, theme_key):
        theme_manager.set_theme(theme_key)
        # Mémoriser le thème pour le prochain démarrage
        try:
            from nova.utils.config_loader import get_config
            get_config().set("theme", theme_key)
        except Exception:
            pass
        self._mark_active()
        print(f"[settings] Thème changé : {theme_key}")


class SettingsApp(BaseApp):
    """Application Réglages complète."""

    app_name = "Réglages"
    app_icon = "settings"
    app_id = "settings"

    def __init__(self, **kwargs):
        # Charger les valeurs enregistrées (persistance entre sessions)
        from nova.utils.config_loader import get_config
        self._config = get_config()
        audio = self._config.get("audio", {}) or {}
        self.brightness = int(audio.get("brightness", 80))
        self.volume = int(audio.get("volume", 60))
        self.notifications = bool(self._config.get("notifications", True))
        self.auto_update = bool(self._config.get("auto_update", False))
        super().__init__(**kwargs)

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ScrollView pour le contenu
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

        # ─── SECTION THÈME ─────────────────────────────────────────
        content.add_widget(self._section_title("Apparence"))

        theme_card = GlassCard(
            size_hint=(1, None),
            height=dp(100),
            corner_radius=dp(2)
        )
        theme_card.add_widget(Label(
            text="Thème actuel : " + theme_manager.get_current_name(),
            font_size=dp(14),
            color=theme_manager.get_color("text"),
            pos_hint={'x': 0.05, 'top': 0.9},
            size_hint=(0.9, 0.3)
        ))

        selector = ThemeSelector(
            pos_hint={'center_x': 0.5, 'y': 0.1},
            size_hint=(0.9, None),
            height=dp(60)
        )
        theme_card.add_widget(selector)
        content.add_widget(theme_card)

        # ─── SECTION AFFICHAGE ─────────────────────────────────────
        content.add_widget(self._section_title("Affichage"))

        # Luminosité
        brightness_slider = Slider(
            min=10, max=100, value=self.brightness,
            size=(dp(150), dp(40))
        )
        brightness_slider.bind(value=self._on_brightness)
        content.add_widget(SettingsRow(
            "Luminosité",
            f"{self.brightness}%",
            brightness_slider
        ))

        # ─── SECTION SON ───────────────────────────────────────────
        content.add_widget(self._section_title("Son"))

        volume_slider = Slider(
            min=0, max=100, value=self.volume,
            size=(dp(150), dp(40))
        )
        volume_slider.bind(value=self._on_volume)
        content.add_widget(SettingsRow(
            "Volume",
            f"{self.volume}%",
            volume_slider
        ))

        # ─── SECTION CONNECTIVITÉ (MOCK) ───────────────────────────
        content.add_widget(self._section_title("Connectivité"))

        # WiFi (mock)
        wifi_actif = bool((self._config.get("wifi", {}) or {}).get("auto_connect", True))
        wifi_switch = Switch(active=wifi_actif, size=(dp(50), dp(30)))
        wifi_switch.bind(active=self._on_wifi)
        self.wifi_row = SettingsRow(
            "WIFI",
            "CONNECTE — NOVA_NETWORK" if wifi_actif else "DESACTIVE",
            wifi_switch
        )
        content.add_widget(self.wifi_row)

        # Bluetooth (mock)
        bt_actif = bool(self._config.get("bluetooth_enabled", False))
        bt_switch = Switch(active=bt_actif, size=(dp(50), dp(30)))
        bt_switch.bind(active=self._on_bluetooth)
        content.add_widget(SettingsRow(
            "Bluetooth",
            "Désactivé",
            bt_switch
        ))

        # ─── SECTION SYSTÈME ───────────────────────────────────────
        content.add_widget(self._section_title(" Système"))

        notif_switch = Switch(active=self.notifications, size=(dp(50), dp(30)))
        notif_switch.bind(active=self._on_notifications)
        content.add_widget(SettingsRow(
            "Notifications",
            "Rappels et alertes",
            notif_switch
        ))

        update_switch = Switch(active=self.auto_update, size=(dp(50), dp(30)))
        content.add_widget(SettingsRow(
            "Mises à jour auto",
            "Télécharger automatiquement",
            update_switch
        ))

        # ─── INFOS SYSTÈME ─────────────────────────────────────────
        content.add_widget(self._section_title("ℹ Informations"))

        info_card = GlassCard(
            size_hint=(1, None),
            height=dp(150),
            corner_radius=dp(2)
        )
        infos = [
            ("Version NOVA", "v0.2.0-beta"),
            ("Système", "Raspberry Pi OS Lite 64-bit"),
            ("Python", "3.11.x"),
            ("Kivy", "2.3.0"),
            ("Espace libre", "45.2 GB / 59.5 GB"),
        ]
        y_pos = 0.85
        for label, value in infos:
            info_card.add_widget(Label(
                text=label,
                font_size=dp(12),
                color=theme_manager.get_color("text_secondary"),
                pos_hint={'x': 0.05, 'top': y_pos},
                size_hint=(0.4, 0.15),
                halign='left'
            ))
            info_card.add_widget(Label(
                text=value,
                font_size=dp(12),
                color=theme_manager.get_color("text"),
                pos_hint={'right': 0.95, 'top': y_pos},
                size_hint=(0.5, 0.15),
                halign='right'
            ))
            y_pos -= 0.18

        content.add_widget(info_card)

        # ─── BOUTON REDÉMARRER ─────────────────────────────────────
        restart_btn = NeonButton(
            icon="restart_alt", text="Redemarrer NOVA",
            size_hint=(1, None),
            height=dp(50),
            corner_radius=dp(2)
        )
        restart_btn.bind(on_press=self._restart)
        content.add_widget(restart_btn)

        scroll.add_widget(content)
        main.add_widget(scroll)

    def _section_title(self, text):
        """Crée un titre de section."""
        return Label(
            text=text,
            font_size=dp(16),
            bold=True,
            color=theme_manager.get_color("primary"),
            size_hint=(1, None),
            height=dp(30),
            halign='left'
        )

    def _on_wifi(self, instance, value):
        """Active/desactive le WiFi (sauvegarde + action reelle sur le Pi)."""
        wifi = dict(self._config.get("wifi", {}) or {})
        wifi["auto_connect"] = bool(value)
        self._config.set("wifi", wifi)
        if hasattr(self, "wifi_row"):
            self.wifi_row.set_subtitle(
                "CONNECTE — NOVA_NETWORK" if value else "DESACTIVE")
        try:
            from nova.utils.platform_utils import is_raspberry_pi
            if is_raspberry_pi():
                import subprocess
                subprocess.run(["nmcli", "radio", "wifi", "on" if value else "off"],
                               capture_output=True, timeout=3)
        except Exception as error:
            print("[settings] wifi :", error)
        print("[settings] WiFi :", "active" if value else "desactive")

    def _on_bluetooth(self, instance, value):
        """Active/desactive le Bluetooth (sauvegarde + action reelle sur le Pi)."""
        self._config.set("bluetooth_enabled", bool(value))
        try:
            from nova.utils.platform_utils import is_raspberry_pi
            if is_raspberry_pi():
                import subprocess
                subprocess.run(["bluetoothctl", "power", "on" if value else "off"],
                               capture_output=True, timeout=3)
        except Exception as error:
            print("[settings] bluetooth :", error)
        print("[settings] Bluetooth :", "active" if value else "desactive")

    def _on_brightness(self, instance, value):
        self.brightness = int(value)
        audio = dict(self._config.get("audio", {}) or {})
        audio["brightness"] = self.brightness
        self._config.set("audio", audio)   # sauvegarde automatique
        self._apply_brightness(self.brightness)
        print(f"[settings] Luminosité : {self.brightness}%")

    def _apply_brightness(self, value):
        """Applique la luminosité à l'écran (réel sur le Pi, sinon ignoré)."""
        try:
            from nova.utils.platform_utils import is_raspberry_pi
            if is_raspberry_pi():
                # Emplacement pour le contrôle réel du rétroéclairage, ex. :
                #   Path("/sys/class/backlight/.../brightness").write_text(...)
                pass
        except Exception:
            pass

    def _on_volume(self, instance, value):
        self.volume = int(value)
        audio = dict(self._config.get("audio", {}) or {})
        audio["volume"] = self.volume
        self._config.set("audio", audio)   # sauvegarde automatique
        self._apply_volume(self.volume)
        print(f"[settings] Volume : {self.volume}%")

    def _apply_volume(self, value):
        """Applique le volume système (réel sur le Pi via amixer, sinon ignoré)."""
        try:
            from nova.utils.platform_utils import is_raspberry_pi
            if is_raspberry_pi():
                import subprocess
                subprocess.run(["amixer", "sset", "Master", "{}%".format(value)],
                               capture_output=True, timeout=2)
        except Exception:
            pass

    def _on_notifications(self, instance, value):
        self.notifications = value
        self._config.set("notifications", bool(value))
        print(f"[settings] Notifications : {value}")

    def _restart(self, instance):
        print("[settings] Redémarrage demandé...")
        # Relancer proprement le processus NOVA
        try:
            import os, sys
            os._exit(42)  # code 42 : un script de lancement peut relancer
        except Exception as error:
            print("[settings] redémarrage impossible :", error)


NovaApp = SettingsApp
