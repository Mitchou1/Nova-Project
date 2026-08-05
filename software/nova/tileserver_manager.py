#!/usr/bin/env python3
"""Gestion automatique du serveur de tuiles local (TileServer-GL).

Démarre le conteneur Docker TileServer-GL quand on entre dans Maps, et l'arrête
quand on en sort — pour économiser la RAM du Raspberry Pi. Un délai de grâce
évite de redémarrer le serveur si l'utilisateur ressort puis revient vite.

Le serveur sert la carte de la Tunisie (tunisia.mbtiles) en local, donc la
carte fonctionne 100% hors ligne une fois le MBTiles généré.
"""

import os
import subprocess
import threading
import time
import urllib.request

# Nom fixe du conteneur (pour pouvoir l'arrêter proprement)
CONTAINER_NAME = "nova-tileserver"
# Port local exposé par TileServer-GL
TILE_PORT = 8080
# Délai de grâce avant arrêt réel (secondes) : si on revient dans Maps
# pendant ce temps, le serveur n'est pas redémarré.
GRACE_PERIOD = 10


class TileServerManager:
    """Démarre/arrête TileServer-GL selon l'entrée/sortie de l'app Maps."""

    def __init__(self, maps_data_dir, mbtiles="tunisia.mbtiles"):
        self.maps_data_dir = maps_data_dir
        self.mbtiles = mbtiles
        self._running = False
        self._stop_timer = None
        self._lock = threading.Lock()

    # --- état ------------------------------------------------------------
    def is_ready(self):
        """Le serveur répond-il sur le port ?"""
        try:
            urllib.request.urlopen(
                "http://localhost:{}/health".format(TILE_PORT), timeout=1)
            return True
        except Exception:
            # /health n'existe pas forcément : tester la racine
            try:
                urllib.request.urlopen(
                    "http://localhost:{}/".format(TILE_PORT), timeout=1)
                return True
            except Exception:
                return False

    def _container_exists(self):
        try:
            out = subprocess.run(
                ["docker", "ps", "-a", "-q", "-f", "name=" + CONTAINER_NAME],
                capture_output=True, text=True, timeout=5)
            return bool(out.stdout.strip())
        except Exception:
            return False

    # --- démarrage -------------------------------------------------------
    def start(self, on_ready=None, on_error=None):
        """Démarre le serveur (si pas déjà lancé). Appelle on_ready quand prêt."""
        with self._lock:
            # annuler un arrêt en attente (période de grâce)
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None

            if self._running and self.is_ready():
                if on_ready:
                    on_ready()
                return

        threading.Thread(target=self._do_start, args=(on_ready, on_error),
                         daemon=True).start()

    def _do_start(self, on_ready, on_error):
        # Déjà prêt (lancé hors de NOVA) ?
        if self.is_ready():
            self._running = True
            if on_ready:
                on_ready()
            return

        # Nettoyer un ancien conteneur du même nom
        self._force_remove()

        mbtiles_path = os.path.join(self.maps_data_dir, self.mbtiles)
        if not os.path.exists(mbtiles_path):
            print("[tileserver] fichier introuvable :", mbtiles_path)
            if on_error:
                on_error("carte introuvable")
            return

        cmd = [
            "docker", "run", "--rm", "-d",
            "--name", CONTAINER_NAME,
            "-v", "{}:/data".format(self.maps_data_dir),
            "-p", "{}:8080".format(TILE_PORT),
            "maptiler/tileserver-gl",
            "--file", self.mbtiles,
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
        except Exception as error:
            print("[tileserver] démarrage impossible :", error)
            if on_error:
                on_error(str(error))
            return

        # Attendre que le serveur réponde (jusqu'à ~20 s)
        for _ in range(40):
            if self.is_ready():
                self._running = True
                print("[tileserver] prêt sur le port", TILE_PORT)
                if on_ready:
                    on_ready()
                return
            time.sleep(0.5)

        print("[tileserver] démarré mais ne répond pas à temps")
        if on_error:
            on_error("délai dépassé")

    # --- arrêt (avec période de grâce) -----------------------------------
    def stop(self):
        """Programme l'arrêt du serveur après le délai de grâce."""
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
            self._stop_timer = threading.Timer(GRACE_PERIOD, self._do_stop)
            self._stop_timer.daemon = True
            self._stop_timer.start()

    def _do_stop(self):
        with self._lock:
            self._stop_timer = None
        self._force_remove()
        self._running = False
        print("[tileserver] arrêté")

    def _force_remove(self):
        """Arrête et supprime le conteneur s'il existe."""
        try:
            subprocess.run(["docker", "stop", CONTAINER_NAME],
                           capture_output=True, timeout=15)
        except Exception:
            pass
        try:
            subprocess.run(["docker", "rm", "-f", CONTAINER_NAME],
                           capture_output=True, timeout=10)
        except Exception:
            pass

    def shutdown(self):
        """Arrêt immédiat (à la fermeture de NOVA)."""
        with self._lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None
        self._force_remove()
        self._running = False


_manager = None


def get_tileserver(maps_data_dir=None):
    """Instance partagée du gestionnaire."""
    global _manager
    if _manager is None and maps_data_dir is not None:
        _manager = TileServerManager(maps_data_dir)
    return _manager
