#!/usr/bin/env python3
"""Compatibilité : ancien point d'entrée du serveur de tuiles.

L'ancienne version démarrait TileServer-GL à l'entrée de Maps et SUPPRIMAIT
le conteneur à la sortie (docker rm -f), puis le recréait avec l'option
--file au retour. Or --file ignore maps_data/config.json : le style
« nova-streets » n'existait plus et toute la carte répondait en 404. C'était
la cause de « la carte ne marche plus hors ligne après avoir lancé NOVA ».

Désormais les trois services (tuiles, itinéraire, recherche) sont gérés par
nova.map_services : créés avec --config /data/config.json et
--restart unless-stopped, jamais supprimés. Ce module ne garde que la même
interface pour ne pas casser le code existant qui l'importe.
"""

import threading

from nova.map_services import READY, DOWN, get_map_services

CONTAINER_NAME = "nova-tileserver"
TILE_PORT = 8080


class TileServerManager:
    """Façade sur le service 'tiles' de nova.map_services."""

    def __init__(self, maps_data_dir=None, mbtiles="tunisia.mbtiles"):
        self.maps_data_dir = maps_data_dir
        self.mbtiles = mbtiles

    def is_ready(self):
        return get_map_services().status("tiles")[0] == READY

    def start(self, on_ready=None, on_error=None):
        """Assure le démarrage des services ; rappelle on_ready / on_error
        dès que l'état du serveur de tuiles est connu."""
        services = get_map_services()
        services.start()
        state, reason = services.status("tiles")
        if state == READY:
            if on_ready:
                on_ready()
            return
        if state == DOWN:
            if on_error:
                on_error(reason)
            return

        done = threading.Event()

        def listener(snapshot):
            st, why, _label = snapshot["tiles"]
            if st not in (READY, DOWN) or done.is_set():
                return
            done.set()
            services.remove_listener(listener)
            if st == READY and on_ready:
                on_ready()
            elif st == DOWN and on_error:
                on_error(why)
        services.add_listener(listener)

    def stop(self):
        """Ne fait plus rien : arrêter/supprimer le conteneur à chaque
        sortie de Maps était la cause du bug hors ligne."""

    def shutdown(self):
        """Arrête la surveillance, pas les conteneurs (ils doivent survivre
        à la fermeture de NOVA et au redémarrage du Pi)."""
        get_map_services().shutdown()


_manager = None


def get_tileserver(maps_data_dir=None):
    """Instance partagée (même signature qu'avant)."""
    global _manager
    if _manager is None:
        _manager = TileServerManager(maps_data_dir)
    return _manager
