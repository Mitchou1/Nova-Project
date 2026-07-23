#!/usr/bin/env python3
"""NOVA — Personal AI Wearable Computer. Point d'entrée principal."""

import sys
from pathlib import Path

# Rend importables les packages `nova` et `apps` quel que soit le cwd
SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova.paths import ensure_dirs
from nova.utils.config_loader import get_config
from nova.utils.platform_utils import is_raspberry_pi

ensure_dirs()

# La config Kivy doit être fixée AVANT l'import de kivy.core.window
from kivy.config import Config as KivyConfig

KivyConfig.set("input", "mouse", "mouse,multitouch_on_demand")
KivyConfig.set("kivy", "exit_on_escape", "1")

from kivy.app import App                                          # noqa: E402
from kivy.core.window import Window                               # noqa: E402
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
        theme.set_theme(config.get("theme", "nova_dark"))
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

        return self.sm

    def on_start(self):
        print("[nova] demarrage termine — theme : {}".format(theme.name))

    def on_stop(self):
        home = getattr(self, "home", None)
        if home is not None:
            home.on_cleanup()

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
