#!/usr/bin/env python3
"""
App Settings NOVA — Réglages système complets.

WiFi, Bluetooth, batterie et informations système affichent l'état RÉEL
du Pi (nova/system_status.py), relu à l'ouverture de l'app puis toutes
les 10 s tant qu'elle est ouverte. Basculer un interrupteur agit sur le
système, puis relit l'état pour confirmer ; un échec est affiché en clair.
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

from apps.base_app import BaseApp, CIBLE_MIN, haut_contenu, hauteur_relative
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

        # Titre — Sora, en majuscules (charte : libellés « commandes »).
        # text_size lié à la taille : sans lui, halign='left' est ignoré et
        # le titre s'affichait centré, décalé par rapport à son sous-titre.
        titre = Label(
            text=title.upper(),
            font_name=_f.FONT_DISPLAY, font_size=dp(13), bold=True,
            color=theme_manager.get_color("text"),
            pos_hint={'x': 0.03, 'center_y': 0.66},
            size_hint=(0.6, 0.38),
            halign='left', valign='middle',
        )
        titre.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.add_widget(titre)

        # Sous-titre — label-caps en JetBrains Mono
        self._subtitle_label = None
        if subtitle:
            self._subtitle_label = Label(
                text=subtitle.upper(),
                font_name=_f.FONT_MONO, font_size=dp(9),
                color=theme_manager.get_color("text_secondary"),
                pos_hint={'x': 0.03, 'center_y': 0.28},
                size_hint=(0.6, 0.3),
                halign='left', valign='middle', shorten=True,
                shorten_from='right',
            )
            # sans text_size, halign est ignoré et un long message déborde
            self._subtitle_label.bind(
                size=lambda w, v: setattr(w, "text_size", v))
            self.add_widget(self._subtitle_label)

        # Widget de contrôle (switch, slider, etc.)
        if widget:
            widget.pos_hint = {'right': 0.97, 'center_y': 0.5}
            widget.size_hint = (None, None)
            self.add_widget(widget)

    def set_subtitle(self, texte, erreur=False):
        """Met à jour le sous-titre (ex. état de connexion) ; erreur=True
        l'affiche dans la couleur d'erreur du thème."""
        if self._subtitle_label is not None:
            self._subtitle_label.text = texte.upper()
            self._subtitle_label.color = theme_manager.get_color(
                "error" if erreur else "text_secondary")


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
        # Vrai pendant qu'on recopie l'état réel dans les interrupteurs : ce
        # changement ne doit pas être pris pour un appui de l'utilisateur.
        self._synchro = False
        self._abonnement = None
        self.auto_update = bool(self._config.get("auto_update", False))
        super().__init__(**kwargs)

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ScrollView pour le contenu
        haut = haut_contenu()       # sous l'en-tête commun
        scroll = ScrollView(
            size_hint=(0.95, haut - 0.02),
            pos_hint={'center_x': 0.5, 'top': haut}
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
            size=(dp(150), CIBLE_MIN)
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
            size=(dp(150), CIBLE_MIN)
        )
        volume_slider.bind(value=self._on_volume)
        content.add_widget(SettingsRow(
            "Volume",
            f"{self.volume}%",
            volume_slider
        ))

        # ─── SECTION CONNECTIVITÉ (état réel) ─────────────────────
        content.add_widget(self._section_title("Connectivité"))

        # Interrupteurs désactivés tant que l'état réel n'est pas lu : ils
        # n'affichent plus jamais la valeur de la config comme si c'était
        # l'état du Pi.
        self.wifi_switch = Switch(active=False, disabled=True, size=(dp(50), CIBLE_MIN))
        self.wifi_switch.bind(active=self._on_wifi)
        self.wifi_row = SettingsRow("WIFI", "Lecture de l'état...", self.wifi_switch)
        content.add_widget(self.wifi_row)

        self.bt_switch = Switch(active=False, disabled=True, size=(dp(50), CIBLE_MIN))
        self.bt_switch.bind(active=self._on_bluetooth)
        self.bt_row = SettingsRow("Bluetooth", "Lecture de l'état...", self.bt_switch)
        content.add_widget(self.bt_row)

        # ─── SECTION SYSTÈME ───────────────────────────────────────
        content.add_widget(self._section_title(" Système"))

        self.batterie_row = SettingsRow("Batterie", "Lecture de l'état...")
        content.add_widget(self.batterie_row)

        notif_switch = Switch(active=self.notifications, size=(dp(50), CIBLE_MIN))
        notif_switch.bind(active=self._on_notifications)
        content.add_widget(SettingsRow(
            "Notifications",
            "Rappels et alertes",
            notif_switch
        ))

        update_switch = Switch(active=self.auto_update, size=(dp(50), CIBLE_MIN))
        update_switch.bind(active=self._on_auto_update)
        content.add_widget(SettingsRow(
            "Mises à jour auto",
            "Télécharger automatiquement",
            update_switch
        ))

        # ─── INFOS SYSTÈME ─────────────────────────────────────────
        content.add_widget(self._section_title("ℹ Informations"))

        self._infos = {}
        lignes_infos = [("modele", "Modèle"), ("systeme", "Système"),
                        ("cpu", "Temp. CPU"), ("ip", "Adresse IP"),
                        ("alim", "Alimentation"), ("stockage", "Stockage"),
                        ("version", "Version NOVA"), ("maj", "Mis à jour")]
        info_card = GlassCard(
            size_hint=(1, None),
            height=dp(24) * len(lignes_infos) + dp(20),
            corner_radius=dp(2)
        )
        grille = GridLayout(cols=2, size_hint=(0.92, 0.9),
                            pos_hint={'center_x': 0.5, 'center_y': 0.5})
        for cle, libelle in lignes_infos:
            gauche = Label(text=libelle, font_size=dp(12), size_hint_x=0.32,
                           color=theme_manager.get_color("text_secondary"),
                           halign='left', valign='middle')
            droite = Label(text="...", font_size=dp(12), size_hint_x=0.68,
                           color=theme_manager.get_color("text"),
                           halign='right', valign='middle', shorten=True)
            for lab in (gauche, droite):
                lab.bind(size=lambda w, v: setattr(w, "text_size", v))
            grille.add_widget(gauche)
            grille.add_widget(droite)
            self._infos[cle] = droite
        self._infos["version"].text = "v0.2.0-beta"
        info_card.add_widget(grille)
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

        # Quitter vers le bureau du Pi. Demande une confirmation : sur un
        # écran tactile porté, un effleurement ne doit pas fermer NOVA.
        quitter_btn = NeonButton(
            icon="logout", text="Quitter vers le bureau",
            size_hint=(1, None), height=dp(50), corner_radius=dp(2),
            accent="error")
        quitter_btn.bind(on_press=self._demander_quitter)
        content.add_widget(quitter_btn)

        scroll.add_widget(content)
        main.add_widget(scroll)

    def _on_auto_update(self, instance, value):
        self.auto_update = bool(value)
        self._config.set("auto_update", bool(value))
        print("[settings] Mises a jour auto :", "actif" if value else "inactif")

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

    # ─── État réel : lecture et affichage ────────────────────────
    def on_enter(self, *args):
        """Relit l'état réel dès l'ouverture, puis toutes les 10 s."""
        from nova.system_status import surveillance
        surv = surveillance()
        if self._abonnement is None:
            # Appelé depuis le thread de surveillance : on repasse sur le
            # thread graphique avant de toucher aux widgets.
            self._abonnement = lambda etat: Clock.schedule_once(
                lambda dt: self._afficher_etat(etat), 0)
            surv.abonner(self._abonnement)
        surv.intervalle = 10
        etat = surv.instantane()
        if etat is not None:
            self._afficher_etat(etat)        # dernier état connu, tout de suite
        surv.rafraichir_maintenant()

    def on_leave(self, *args):
        from nova.system_status import surveillance
        surv = surveillance()
        surv.intervalle = 30                 # rythme de fond (bandeau d'accueil)
        if self._abonnement is not None:
            surv.desabonner(self._abonnement)
            self._abonnement = None

    def _regler_switch(self, switch, etat):
        """Recopie un état réel dans un interrupteur sans déclencher d'action."""
        self._synchro = True
        try:
            switch.disabled = not etat.get("disponible")
            if etat.get("actif") is not None:
                switch.active = bool(etat["actif"])
        finally:
            self._synchro = False

    def _afficher_etat(self, etat):
        import time as _time
        wifi = etat["wifi"]
        if not getattr(self.wifi_switch, "_en_cours", False):
            self._regler_switch(self.wifi_switch, wifi)
            if wifi.get("erreur"):
                self.wifi_row.set_subtitle("Indisponible : " + wifi["erreur"], erreur=True)
            elif not wifi["actif"]:
                self.wifi_row.set_subtitle("Désactivé")
            elif wifi.get("ssid"):
                signal = " — signal {} %".format(wifi["signal"]) if wifi.get("signal") is not None else ""
                self.wifi_row.set_subtitle("Connecté : {}{}".format(wifi["ssid"], signal))
            else:
                self.wifi_row.set_subtitle("Activé — non connecté")

        bt = etat["bluetooth"]
        if not getattr(self.bt_switch, "_en_cours", False):
            self._regler_switch(self.bt_switch, bt)
            if bt.get("erreur"):
                self.bt_row.set_subtitle("Indisponible : " + bt["erreur"], erreur=True)
            elif not bt["actif"]:
                self.bt_row.set_subtitle("Désactivé")
            else:
                appareils = bt.get("appareils") or []
                self.bt_row.set_subtitle(
                    "Activé — {} appareil(s) appairé(s){}".format(
                        len(appareils), " : " + ", ".join(appareils[:3]) if appareils else ""))

        bat = etat["batterie"]
        if bat["simule"]:
            self.batterie_row.set_subtitle(
                "SIMULATION — {}".format(bat.get("raison") or "aucune mesure réelle"),
                erreur=True)
        else:
            morceaux = ["{:.0f} %".format(bat["pourcent"])]
            if bat.get("tension"):
                morceaux.append("{:.2f} V".format(bat["tension"]))
            if bat.get("en_charge") is not None:
                morceaux.append("en charge" if bat["en_charge"] else "sur batterie")
            morceaux.append(bat["source"])
            self.batterie_row.set_subtitle(" — ".join(morceaux))

        st = etat["stockage"]
        self._infos["modele"].text = etat.get("modele") or "?"
        self._infos["systeme"].text = etat.get("systeme") or "?"
        self._infos["cpu"].text = ("{:.1f} °C".format(etat["cpu_temp"])
                                   if etat.get("cpu_temp") is not None else "non disponible")
        self._infos["ip"].text = etat.get("ip") or "aucune (hors réseau)"
        self._infos["alim"].text = etat["alimentation"]["detail"]
        self._infos["stockage"].text = ("{:.1f} Go libres / {:.1f} Go".format(
            st["libre_go"], st["total_go"]) if st.get("total_go") else "?")
        self._infos["maj"].text = _time.strftime("%H:%M:%S", _time.localtime(etat["horodatage"]))

    # ─── Bascules WiFi / Bluetooth : action réelle + vérification ──
    def _basculer(self, switch, row, valeur, fonction, nom):
        """Lance la commande système dans un thread, puis relit l'état. En
        cas d'échec, le message s'affiche et l'interrupteur revient à l'état
        RÉEL (avant : il restait sur la valeur demandée, même si rien
        n'avait changé)."""
        if self._synchro:
            return
        import threading
        from nova.system_status import surveillance
        switch._en_cours = True
        switch.disabled = True
        row.set_subtitle("{}...".format("Activation" if valeur else "Désactivation"))

        def travail():
            reussi, erreur = fonction(valeur)
            print("[settings] {} {} : {}".format(nom, "on" if valeur else "off",
                                                 "OK" if reussi else erreur))
            etat = surveillance().rafraichir()       # relecture pour confirmer

            def fin(_dt):
                switch._en_cours = False
                if etat is not None:
                    self._afficher_etat(etat)
                if not reussi:
                    row.set_subtitle("Échec : {}".format(erreur), erreur=True)
            Clock.schedule_once(fin, 0)
        threading.Thread(target=travail, daemon=True).start()

    def _on_wifi(self, instance, value):
        from nova.system_status import basculer_wifi
        self._basculer(self.wifi_switch, self.wifi_row, bool(value), basculer_wifi, "WiFi")

    def _on_bluetooth(self, instance, value):
        from nova.system_status import basculer_bluetooth
        self._basculer(self.bt_switch, self.bt_row, bool(value), basculer_bluetooth, "Bluetooth")

    def _on_brightness(self, instance, value):
        self.brightness = int(value)
        audio = dict(self._config.get("audio", {}) or {})
        audio["brightness"] = self.brightness
        self._config.set("audio", audio)   # sauvegarde automatique
        self._apply_brightness(self.brightness)
        print(f"[settings] Luminosité : {self.brightness}%")

    # Ecrans tactiles officiels Raspberry Pi les plus courants : premier
    # chemin de backlight sysfs trouve = celui utilise.
    _CHEMINS_BACKLIGHT = (
        "/sys/class/backlight/rpi_backlight/brightness",
        "/sys/class/backlight/10-0045/brightness",
    )

    def _apply_brightness(self, value):
        """Applique la luminosite au retroeclairage reel sur le Pi (si un
        des chemins backlight connus existe), sinon ignore proprement."""
        try:
            from nova.utils.platform_utils import is_raspberry_pi
            if not is_raspberry_pi():
                return
            from pathlib import Path
            for chemin in self._CHEMINS_BACKLIGHT:
                cible = Path(chemin)
                if not cible.exists():
                    continue
                max_brightness = 255
                max_path = cible.parent / "max_brightness"
                if max_path.exists():
                    max_brightness = int(max_path.read_text().strip())
                niveau = max(1, round(max_brightness * value / 100.0))
                cible.write_text(str(niveau))
                return
        except Exception as error:
            print("[settings] luminosite :", error)

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

    def _demander_quitter(self, *_a):
        """Confirmation avant de fermer NOVA et revenir au bureau du Pi."""
        from kivy.uix.popup import Popup
        boite = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(12))
        boite.add_widget(Label(
            text="Fermer NOVA et revenir au bureau du Raspberry Pi ?\n"
                 "Relance : ./start_nova.sh ou redémarrage du Pi.",
            color=theme_manager.get_color("text"), halign="center"))
        boutons = BoxLayout(size_hint=(1, None), height=CIBLE_MIN, spacing=dp(12))
        annuler = NeonButton(text="Annuler", corner_radius=dp(2))
        confirmer = NeonButton(icon="logout", text="Quitter", accent="error",
                               corner_radius=dp(2))
        boutons.add_widget(annuler)
        boutons.add_widget(confirmer)
        boite.add_widget(boutons)
        popup = Popup(title="QUITTER NOVA", content=boite, size_hint=(0.7, 0.5),
                      auto_dismiss=True)
        annuler.bind(on_press=lambda *_a: popup.dismiss())
        confirmer.bind(on_press=lambda *_a: (popup.dismiss(), quitter_nova()))
        popup.open()

    def _restart(self, instance):
        print("[settings] Redémarrage demandé...")
        # Relancer proprement le processus NOVA
        try:
            import os, sys
            os._exit(42)  # code 42 : un script de lancement peut relancer
        except Exception as error:
            print("[settings] redémarrage impossible :", error)


def quitter_nova(delai=0.3):
    """Ferme NOVA proprement (code de sortie 0) : start_nova.sh ne le relance
    pas (il ne relance que sur le code 42 de « Redémarrer »), on retrouve
    donc le bureau du Pi. App.stop() passe par on_stop (nettoyage)."""
    from kivy.app import App
    print("[settings] fermeture de NOVA demandée : retour au bureau")
    Clock.schedule_once(lambda dt: App.get_running_app().stop(), delai)


NovaApp = SettingsApp
