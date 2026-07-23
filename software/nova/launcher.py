#!/usr/bin/env python3
"""Découverte et chargement dynamique des applications (plugins)."""

import importlib
import sys
import traceback

from nova.paths import APPS_DIR, SOFTWARE_DIR


class AppLauncher:
    """Scanne software/apps/ et instancie chaque application trouvée."""

    def __init__(self, screen_manager):
        self.sm = screen_manager
        self.loaded_apps = {}
        if str(SOFTWARE_DIR) not in sys.path:
            sys.path.insert(0, str(SOFTWARE_DIR))

    def discover_apps(self):
        """Retourne la liste des dossiers d'applications valides."""
        found = []
        if not APPS_DIR.exists():
            print("[launcher] dossier introuvable : {}".format(APPS_DIR))
            return found

        for folder in sorted(APPS_DIR.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name.startswith(("_", ".")):
                continue
            if (folder / "app.py").exists():
                found.append(folder.name)
        return found

    def load_app(self, app_name):
        """Importe apps.<app_name>.app et ajoute l'écran au ScreenManager."""
        try:
            module = importlib.import_module("apps.{}.app".format(app_name))
        except Exception:
            print("[launcher] import impossible : {}".format(app_name))
            traceback.print_exc()
            return False

        app_class = getattr(module, "NovaApp", None)
        if app_class is None:
            print("[launcher] {} : classe NovaApp absente".format(app_name))
            return False

        try:
            instance = app_class()
            self.sm.add_widget(instance)
        except Exception:
            print("[launcher] instanciation impossible : {}".format(app_name))
            traceback.print_exc()
            return False

        self.loaded_apps[app_name] = {
            "class": app_class,
            "instance": instance,
            "screen": getattr(app_class, "app_id", app_name),
            "display_name": getattr(app_class, "app_name", app_name),
            "icon": getattr(app_class, "app_icon", "•"),
        }
        print("[launcher] app chargee : {}".format(app_name))
        return True

    def load_all_apps(self):
        """Charge toutes les applications découvertes, retourne le total."""
        for name in self.discover_apps():
            self.load_app(name)
        return len(self.loaded_apps)

    def get_app(self, app_name):
        return self.loaded_apps.get(app_name)

    def list_apps(self):
        return list(self.loaded_apps)

    def get_app_info(self):
        """Infos d'affichage pour la grille de l'écran d'accueil."""
        return [
            {"id": name, "name": info["display_name"], "icon": info["icon"]}
            for name, info in self.loaded_apps.items()
        ]

    def launch_app(self, app_name):
        info = self.loaded_apps.get(app_name)
        if info is None:
            print("[launcher] app inconnue : {}".format(app_name))
            return False
        self.sm.current = info["screen"]
        return True

    def cleanup(self):
        """Appelle on_cleanup() sur chaque app qui l'implémente."""
        for name, info in self.loaded_apps.items():
            hook = getattr(info["instance"], "on_cleanup", None)
            if callable(hook):
                try:
                    hook()
                except Exception as error:
                    print("[launcher] cleanup {} : {}".format(name, error))
