#!/usr/bin/env python3
"""NOVA — Personal AI Wearable Computer. Point d'entrée principal."""

import sys
from pathlib import Path

# Rend importables les packages `nova` et `apps` quel que soit le cwd
SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova import fonts
from nova.paths import ensure_dirs

# Les polices doivent être enregistrées avant la création du moindre Label
fonts.register_fonts()
from nova.utils.config_loader import get_config
from nova.utils.platform_utils import is_raspberry_pi

ensure_dirs()

# La config Kivy doit être fixée AVANT l'import de kivy.core.window
from kivy.config import Config as KivyConfig

KivyConfig.set("input", "mouse", "mouse,multitouch_on_demand")
KivyConfig.set("kivy", "exit_on_escape", "1")

# Clavier virtuel NOVA (nova/ui/nova_keyboard.py) plutôt que celui du
# système : ce dernier recouvrait les champs sans que NOVA puisse connaître
# sa hauteur. « systemanddock » garde le clavier physique utilisable (PC,
# clavier USB) tout en affichant le clavier NOVA docké en bas.
# SDL_ENABLE_SCREEN_KEYBOARD=0 : SDL ne demande pas en plus le clavier
# visuel de l'OS. Désactivable par "virtual_keyboard": false dans la config.
import os                                                         # noqa: E402

CLAVIER_NOVA = bool(get_config().get("virtual_keyboard", True))
if CLAVIER_NOVA:
    os.environ.setdefault("SDL_ENABLE_SCREEN_KEYBOARD", "0")
    KivyConfig.set("kivy", "keyboard_mode", "systemanddock")

from kivy.app import App                                          # noqa: E402
import time
from kivy.clock import Clock
from kivy.core.window import Window                               # noqa: E402

if CLAVIER_NOVA:
    from nova.ui.nova_keyboard import NovaKeyboard                # noqa: E402
    Window.set_vkeyboard_class(NovaKeyboard)
from kivy.uix.screenmanager import ScreenManager                  # noqa: E402

from nova.launcher import AppLauncher                             # noqa: E402
from nova.ui.home_screen import HomeScreen                        # noqa: E402
from nova.ui.theme import theme                                   # noqa: E402
from nova.ui.transitions import make_transition                   # noqa: E402


class NovaApp(App):
    """Application Kivy principale."""

    title = "NOVA"

    def build(self):
        config = get_config()
        theme.set_theme(config.get("theme", "classic"))
        Window.clearcolor = theme.get_rgba("background")

        if is_raspberry_pi():
            Window.fullscreen = "auto"
            Window.show_cursor = False
        else:
            screen = config.get("screen", {})
            Window.size = (screen.get("width", 800), screen.get("height", 480))

        self.sm = ScreenManager(transition=make_transition())

        # L'écran d'accueil doit exister avant les apps : c'est l'écran par
        # défaut vers lequel chaque application revient.
        self.home = HomeScreen()
        self.sm.add_widget(self.home)

        # Le launcher enregistre chaque application comme un écran du
        # ScreenManager : sans lui, `manager.current = "settings"` échoue.
        self.launcher = AppLauncher(self.sm)
        count = self.launcher.load_all_apps()
        self.home.bind_launcher(self.launcher)
        print("[nova] {} application(s) chargee(s)".format(count))

        # Racine : le gestionnaire d'ecrans, surmonte de la veille et des
        # alertes de rendez-vous (qui doivent couvrir toute l'interface).
        from kivy.uix.floatlayout import FloatLayout
        from nova.ui.sleep_screen import SleepOverlay
        from nova.ui.event_alert import EventAlert

        self.root_layout = FloatLayout()
        self.sm.size_hint = (1, 1)
        self.sm.pos_hint = {"x": 0, "y": 0}
        self.root_layout.add_widget(self.sm)
        if CLAVIER_NOVA:
            # Seuls les écrans remontent au-dessus du clavier ; les couches
            # de veille et d'alerte ci-dessous restent plein écran.
            from nova.ui.nova_keyboard import set_lift_target
            set_lift_target(self.sm)

        # Les deux couches doivent couvrir TOUT l'ecran : sans size_hint
        # explicite elles restaient a 100x100 px et cassaient l'affichage.
        self.sleep_overlay = SleepOverlay(
            on_wake=self.wake_up,
            size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self.root_layout.add_widget(self.sleep_overlay)

        self.event_alert = EventAlert(
            size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self.root_layout.add_widget(self.event_alert)

        # Veille automatique + surveillance des rendez-vous
        self._last_touch = time.time()
        self._asleep = False
        Window.bind(on_touch_down=self._on_any_touch)
        Clock.schedule_interval(self._check_idle, 1.0)
        Clock.schedule_interval(self._check_events, 20.0)
        Clock.schedule_interval(self._check_power, 30.0)
        self._check_power(0)

        return self.root_layout

    # ------------------------------------------------------------------
    # Mode economie d'energie (cahier des charges, Phase 10)
    # ------------------------------------------------------------------
    def _check_power(self, _dt):
        """Coupe animations/particules quand la batterie passe sous le seuil."""
        try:
            from nova.power_manager import refresh_low_power_state, is_low_power_active
            if refresh_low_power_state():
                actif = is_low_power_active()
                print("[nova] mode economie d'energie :", "active" if actif else "desactive")
        except Exception as error:
            print("[nova] verification batterie :", error)

    # ------------------------------------------------------------------
    # Veille automatique
    # ------------------------------------------------------------------
    def _sleep_delay(self):
        """Delai d'inactivite avant la veille, en secondes (reglable)."""
        try:
            return float(get_config().get("sleep_seconds", 5))
        except (TypeError, ValueError):
            return 5.0

    def _on_any_touch(self, _window, _touch):
        """Tout contact remet le compteur d'inactivite a zero."""
        self._last_touch = time.time()
        if self._asleep:
            self.wake_up()
        return False           # laisse l'evenement suivre son cours

    def _check_idle(self, _dt):
        if self._asleep or self.event_alert.opacity > 0.05:
            return
        if time.time() - self._last_touch >= self._sleep_delay():
            self.go_to_sleep()

    def go_to_sleep(self):
        """Passe l'appareil en veille (ecran noir + logo anime)."""
        if self._asleep:
            return
        self._asleep = True
        self.sleep_overlay.show()
        print("[nova] veille")

    def wake_up(self):
        """Reveille l'appareil et rend la main a l'ecran precedent."""
        if not self._asleep:
            return
        self._asleep = False
        self._last_touch = time.time()
        self.sleep_overlay.hide()
        print("[nova] reveil")

    # ------------------------------------------------------------------
    # Alerte de rendez-vous a l'heure dite
    # ------------------------------------------------------------------
    def _check_events(self, _dt):
        """Declenche l'alerte des que le delai de rappel de chaque evenement
        est atteint (storage.due_reminders gere le declenchement unique via
        la colonne `notified`, par evenement, avec son propre reminder_minutes)."""
        try:
            from apps.calendar import storage
            for evenement in storage.due_reminders():
                self.show_event_alert(evenement)
        except Exception as error:
            print("[nova] verification des rendez-vous :", error)

    def show_event_alert(self, evenement):
        """Affiche l'alerte plein ecran (reveille l'appareil si besoin)."""
        if self._asleep:
            self.wake_up()
        self._last_touch = time.time()
        self.event_alert.show(evenement)

    def on_start(self):
        print("[nova] demarrage termine — theme : {}".format(theme.name))
        # Moteur IA préchargé en arrière-plan : la première commande ne doit
        # plus attendre le chargement des modèles (~2,4 Go) ni la lecture du
        # prompt système par Qwen.
        try:
            from nova.ai_engine import preload_in_background
            preload_in_background()
        except Exception as error:
            print("[ia] préchargement non lancé :", error)
        # État réel du système (WiFi, Bluetooth, batterie...) relu en
        # arrière-plan : l'accueil et les Paramètres l'affichent sans jamais
        # lancer de commande sur le thread de l'interface.
        try:
            from nova.system_status import surveillance
            # Le bandeau d'état de l'accueil se met à jour dès chaque
            # lecture (sinon « ... » jusqu'à son prochain tour d'horloge)
            surveillance().abonner(lambda _etat: Clock.schedule_once(
                lambda dt: self.home.update_status(), 0))
            surveillance().demarrer()
        except Exception as error:
            print("[systeme] surveillance non démarrée :", error)
        # Services de carte hors ligne (tuiles, itinéraire, recherche) :
        # vérifiés et relancés dès le démarrage, dans leur propre thread,
        # pour qu'ils soient prêts avant même d'ouvrir Maps sans jamais
        # bloquer l'affichage de l'accueil.
        try:
            from nova.map_services import get_map_services
            get_map_services().start()
        except Exception as error:
            print("[cartes] gestionnaire non démarré :", error)

    def on_stop(self):
        home = getattr(self, "home", None)
        if home is not None:
            home.on_cleanup()

        # Arrêter la SURVEILLANCE des services de carte. Les conteneurs,
        # eux, restent actifs (--restart unless-stopped) : les supprimer à la
        # fermeture obligeait à tout relancer et cassait le hors ligne.
        try:
            from nova.map_services import get_map_services
            get_map_services().shutdown()
        except Exception:
            pass

        launcher = getattr(self, "launcher", None)
        if launcher is not None:
            launcher.cleanup()

        try:
            from nova.power_manager import get_power_manager
            get_power_manager().cleanup()
        except Exception:
            pass


def main():
    NovaApp().run()


if __name__ == "__main__":
    main()
