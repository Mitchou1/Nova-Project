#!/usr/bin/env python3
"""
Gestionnaire d'applications (plugins)
"""

import os
import sys
import importlib.util
from pathlib import Path

APPS_DIR = Path(__file__).parent.parent / "apps"

class AppLauncher:
    """Charge et gère les applications dynamiquement"""

    def __init__(self, screen_manager):
        self.sm = screen_manager
        self.loaded_apps = {}
        self.discover_apps()

    def discover_apps(self):
        """Scanne le dossier /apps et détecte les applications"""
        if not APPS_DIR.exists():
            print(f"⚠️ Dossier apps non trouvé: {APPS_DIR}")
            return

        for app_folder in sorted(APPS_DIR.iterdir()):
            if app_folder.is_dir() and not app_folder.name.startswith('_'):
                app_file = app_folder / "app.py"
                if app_file.exists():
                    self.load_app(app_folder.name, app_file)

    def load_app(self, app_name, app_path):
        """Charge dynamiquement une application"""
        try:
            spec = importlib.util.spec_from_file_location(
                f"apps.{app_name}", app_path
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"apps.{app_name}"] = module
            spec.loader.exec_module(module)

            if hasattr(module, 'NovaApp'):
                app_class = module.NovaApp
                # Instancier et ajouter au screen manager
                app_instance = app_class()
                self.sm.add_widget(app_instance)
                self.loaded_apps[app_name] = {
                    'class': app_class,
                    'instance': app_instance,
                    'name': getattr(app_class, 'app_id', app_name),
                    'display_name': getattr(app_class, 'app_name', app_name),
                    'icon': getattr(app_class, 'app_icon', '📱')
                }
                print(f"✅ App chargée : {app_name}")
            else:
                print(f"⚠️  {app_name} : pas de classe NovaApp trouvée")

        except Exception as e:
            print(f"❌ Erreur chargement {app_name} : {e}")

    def load_all_apps(self):
        """Toutes les apps sont deja chargees par discover_apps() ; renvoie
        leur nombre (main.py l'affiche au demarrage)."""
        return len(self.loaded_apps)

    def get_app(self, app_name):
        """Retourne les infos d'une application"""
        return self.loaded_apps.get(app_name)

    def list_apps(self):
        """Liste toutes les apps disponibles"""
        return list(self.loaded_apps.keys())

    def get_app_info(self):
        """Retourne les infos de toutes les apps pour l'affichage"""
        return [
            {
                'id': name,
                'name': info['display_name'],
                'icon': info['icon']
            }
            for name, info in self.loaded_apps.items()
        ]

    def launch_app(self, app_name):
        """Lance une application par son ID"""
        if app_name in self.loaded_apps:
            app_id = self.loaded_apps[app_name]['name']
            self.sm.current = app_id
            return True
        return False

    def cleanup(self):
        """Nettoyage à l'arrêt"""
        pass
