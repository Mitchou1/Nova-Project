#!/usr/bin/env python3
"""Gestionnaire des services cartographiques hors ligne de NOVA.

Trois conteneurs Docker rendent la carte 100 % hors ligne :
  - nova-tileserver (TileServer-GL, port 8080) : les tuiles de la carte
  - nova-valhalla   (Valhalla,      port 8002) : le calcul d'itinéraire
  - nova-nominatim  (Nominatim,     port 8088) : la recherche d'adresse

Pourquoi ce module existe (bug récurrent « la carte ne marche qu'avec
internet ») : l'ancien tileserver_manager SUPPRIMAIT le conteneur à chaque
sortie de Maps puis le recréait avec l'option --file, qui ne connaît pas le
style « nova-streets » -> toutes les tuiles en 404. Et aucun conteneur
n'avait de politique de redémarrage, donc rien ne survivait à un reboot.

Règles appliquées ici :
  - on ne supprime JAMAIS un conteneur (Nominatim met des heures à
    réimporter sa base : le supprimer serait catastrophique) ;
  - conteneur absent -> créé avec --restart unless-stopped ;
  - conteneur existant sans politique de redémarrage -> corrigé via
    `docker update`, sans le recréer ;
  - conteneur arrêté -> `docker start` ;
  - un service n'est déclaré « prêt » que s'il fait VRAIMENT son travail
    (le style de carte existe, Valhalla calcule un trajet réel, Nominatim
    répond OK) — pas seulement parce que son port est ouvert ;
  - chaque panne est journalisée avec sa cause précise.
"""

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

from nova.paths import ROOT_DIR

# États possibles d'un service
READY = "ready"         # répond et fait son travail
STARTING = "starting"   # conteneur lancé, pas encore opérationnel
DOWN = "down"           # indisponible (la raison est dans l'état)

# Intervalle de surveillance une fois tout prêt : une requête HTTP locale
# toutes les 30 s ne coûte presque rien et détecte un conteneur tombé.
WATCH_INTERVAL = 30
# Pendant le démarrage, on vérifie plus souvent pour afficher vite « prêt »
STARTUP_INTERVAL = 3
# On ne relance pas un même conteneur plus d'une fois par minute : évite une
# boucle start/crash qui ferait chauffer le Pi pour rien.
RESTART_COOLDOWN = 60
# Au-delà, un service toujours pas prêt est signalé comme en panne (mais on
# continue de le surveiller : Valhalla peut construire ses tuiles longtemps).
STARTUP_TIMEOUT = 600

TILE_STYLE = "nova-streets"


def _http_get(url, timeout=2):
    """GET simple ; renvoie (code, corps) ou lève une exception."""
    req = urllib.request.Request(url, headers={"User-Agent": "NOVA/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _check_tileserver():
    """Prêt seulement si le style nova-streets est servi : c'est exactement
    ce que l'ancien bug (--file au lieu de --config) cassait."""
    try:
        code, _ = _http_get(
            "http://localhost:8080/styles/{}/style.json".format(TILE_STYLE))
        return code == 200, ""
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return False, ("style '{}' introuvable : conteneur lancé sans "
                           "--config /data/config.json".format(TILE_STYLE))
        return False, "HTTP {}".format(err.code)
    except Exception:
        return False, "ne répond pas sur le port 8080"


def _check_valhalla():
    """Prêt seulement si Valhalla calcule un vrai trajet. /status répond
    bien avant que les tuiles routières soient chargées : c'était la cause
    de l'itinéraire tracé en ligne droite."""
    body = json.dumps({
        "locations": [{"lat": 36.8065, "lon": 10.1815},
                      {"lat": 36.815, "lon": 10.19}],
        "costing": "auto"}).encode("utf-8")
    try:
        req = urllib.request.Request(
            "http://localhost:8002/route", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("trip", {}).get("legs"):
            return True, ""
        return False, "tuiles routières pas encore chargées"
    except urllib.error.HTTPError:
        return False, "tuiles routières pas encore chargées"
    except Exception:
        return False, "ne répond pas sur le port 8002"


def _check_nominatim():
    try:
        code, body = _http_get("http://localhost:8088/status", timeout=3)
        if code == 200 and body.strip().upper().startswith(b"OK"):
            return True, ""
        return False, "base d'adresses pas encore prête"
    except Exception:
        return False, "ne répond pas sur le port 8088 (import possible en cours)"


class ServiceSpec:
    """Description d'un conteneur : comment le créer et le vérifier."""

    def __init__(self, key, label, container, image, run_args, required,
                 check, image_cmd=None, stateless=False):
        self.key = key
        self.label = label
        self.container = container
        self.image = image
        self.run_args = run_args          # options de `docker run`
        self.image_cmd = image_cmd or []  # arguments passés à l'image
        self.required = required          # fichiers nécessaires à la création
        self.check = check                # () -> (prêt ?, raison)
        # Sans données internes : on peut le recréer s'il est mal configuré.
        # Jamais vrai pour Nominatim (sa base serait perdue).
        self.stateless = stateless


def default_specs(root=ROOT_DIR):
    """Les trois services, avec les MÊMES paramètres que start_nova.sh
    (sinon un conteneur recréé par NOVA se comporterait différemment)."""
    maps = os.path.join(str(root), "maps_data")
    valhalla = os.path.join(str(root), "valhalla_data")
    return [
        ServiceSpec(
            "tiles", "Carte (TileServer)", "nova-tileserver",
            "maptiler/tileserver-gl",
            ["-v", "{}:/data".format(maps), "-p", "8080:8080"],
            [os.path.join(maps, "config.json"),
             os.path.join(maps, "tunisia.mbtiles")],
            _check_tileserver,
            # --config et non --file : --file ignore config.json, donc le
            # style nova-streets n'existe pas et toutes les tuiles sont en 404.
            image_cmd=["--config", "/data/config.json"], stateless=True),
        ServiceSpec(
            "routing", "Itinéraire (Valhalla)", "nova-valhalla",
            "ghcr.io/gis-ops/docker-valhalla/valhalla:latest",
            ["-p", "8002:8002", "-v", "{}:/custom_files".format(valhalla),
             "-e", "tile_urls=/custom_files/tunisia.osm.pbf"],
            [os.path.join(valhalla, "tunisia.osm.pbf")],
            _check_valhalla),
        ServiceSpec(
            "geocoding", "Recherche (Nominatim)", "nova-nominatim",
            "mediagis/nominatim:5.1",
            ["-e", "PBF_PATH=/nominatim/data/tunisia.osm.pbf",
             "-p", "8088:8080", "-v", "{}:/nominatim/data".format(maps),
             "--shm-size=1g"],
            [os.path.join(maps, "tunisia.osm.pbf")],
            _check_nominatim),
    ]


class DockerError(Exception):
    """Erreur Docker traduite en message compréhensible."""


def explain_docker_error(stderr):
    """Transforme une erreur Docker brute en cause lisible + remède."""
    low = (stderr or "").lower()
    if "permission denied" in low:
        return ("accès à Docker refusé : ajoute l'utilisateur au groupe docker "
                "(sudo usermod -aG docker $USER, puis reconnecte-toi)")
    if ("cannot connect to the docker daemon" in low
            or "is the docker daemon running" in low):
        return "service Docker arrêté (sudo systemctl enable --now docker)"
    if "port is already allocated" in low or "address already in use" in low:
        return "port déjà utilisé par un autre programme"
    if ("no such image" in low or "unable to find image" in low
            or "pull access denied" in low):
        return "image Docker absente (et pas d'internet pour la télécharger)"
    lines = (stderr or "").strip().splitlines()
    return lines[-1][:160] if lines else "erreur Docker inconnue"


def _docker(args, timeout=30):
    """Lance une commande docker ; lève DockerError avec une cause claire."""
    try:
        out = subprocess.run(["docker"] + args, capture_output=True,
                             text=True, timeout=timeout)
    except FileNotFoundError:
        raise DockerError("Docker n'est pas installé")
    except subprocess.TimeoutExpired:
        raise DockerError("Docker ne répond pas (délai dépassé)")
    if out.returncode != 0:
        # On garde le texte brut en tête pour que l'appelant puisse
        # reconnaître « No such object » (conteneur absent).
        raise DockerError(explain_docker_error(out.stderr))
    return out.stdout.strip()


class _State:
    def __init__(self, spec):
        self.spec = spec
        self.state = STARTING
        self.reason = "vérification en cours"
        self.since = time.time()
        self.last_restart = 0.0
        self.policy_ok = False     # politique de redémarrage vérifiée ?


class MapServices:
    """Démarre, répare et surveille les trois services en arrière-plan."""

    def __init__(self, specs=None, docker=_docker):
        self._docker = docker
        self._states = {s.key: _State(s)
                        for s in (specs if specs is not None else default_specs())}
        self._lock = threading.Lock()
        self._listeners = []
        self._thread = None
        self._stop = threading.Event()

    # --- API publique -----------------------------------------------------
    def start(self):
        """Lance la surveillance (idempotent). Appelé au démarrage de NOVA."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="map-services",
                                        daemon=True)
        self._thread.start()

    def shutdown(self):
        """Arrête la SURVEILLANCE seulement : les conteneurs restent actifs,
        ils doivent survivre à la fermeture de NOVA et au reboot du Pi."""
        self._stop.set()

    def status(self, key):
        """(état, raison) d'un service : 'tiles', 'routing' ou 'geocoding'."""
        with self._lock:
            st = self._states.get(key)
            return (st.state, st.reason) if st else (DOWN, "service inconnu")

    def snapshot(self):
        """{clé: (état, raison, libellé)} pour tous les services."""
        with self._lock:
            return {k: (s.state, s.reason, s.spec.label)
                    for k, s in self._states.items()}

    def add_listener(self, callback):
        """callback(snapshot) appelé (depuis un thread) à chaque changement."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def check_now(self):
        """Une passe complète immédiate (utilisée par la boucle et les tests)."""
        for st in list(self._states.values()):
            self._check_one(st)

    # --- boucle -------------------------------------------------------------
    def _run(self):
        print("[cartes] vérification des services hors ligne...")
        while not self._stop.is_set():
            self.check_now()
            all_ready = all(s.state == READY for s in self._states.values())
            self._stop.wait(WATCH_INTERVAL if all_ready else STARTUP_INTERVAL)

    def _check_one(self, st):
        spec = st.spec
        ok, why = spec.check()
        if ok:
            # Même un service qui marche doit survivre au reboot du Pi :
            # on vérifie sa politique de redémarrage une fois par session.
            if not st.policy_ok:
                try:
                    self._ensure_restart_policy(spec)
                    st.policy_ok = True
                except DockerError as err:
                    # Service utilisable quand même (lancé hors Docker, ou
                    # droits Docker manquants) : on le signale sans bloquer.
                    print("[cartes] {} : politique de redémarrage non "
                          "vérifiable ({})".format(spec.container, err))
                    st.policy_ok = True
            self._set(st, READY, "")
            return

        # Le service ne répond pas : l'état du conteneur dit pourquoi
        try:
            status = self._container_status(spec)
            if status is None:
                self._create(spec)
                st.last_restart = time.time()
                self._set(st, STARTING, "conteneur créé, démarrage...")
                return
            self._ensure_restart_policy(spec)
            if status != "running":
                if time.time() - st.last_restart >= RESTART_COOLDOWN:
                    st.last_restart = time.time()
                    print("[cartes] {} était arrêté ({}) : redémarrage".format(
                        spec.container, status))
                    self._docker(["start", spec.container])
                self._set(st, STARTING, "redémarrage du conteneur...")
                return
            if self._misconfigured(spec):
                # Cas de l'ancien bug : TileServer lancé avec --file. Il
                # tourne mais ne sert pas le bon style -> on le recrée.
                print("[cartes] {} lancé avec de mauvais arguments : "
                      "recréation".format(spec.container))
                self._docker(["rm", "-f", spec.container])
                self._create(spec)
                st.last_restart = time.time()
                self._set(st, STARTING, "conteneur recréé avec --config...")
                return
        except DockerError as err:
            self._set(st, DOWN, str(err))
            return

        # Conteneur en marche mais service pas encore opérationnel
        waited = time.time() - st.since
        if st.state == DOWN or waited > STARTUP_TIMEOUT:
            self._set(st, DOWN, why)
        else:
            self._set(st, STARTING, why)

    # --- Docker -------------------------------------------------------------
    def _container_status(self, spec):
        """'running', 'exited'... ou None si le conteneur n'existe pas."""
        try:
            return self._docker(["inspect", "-f", "{{.State.Status}}",
                                 spec.container], timeout=10)
        except DockerError as err:
            if "no such" in str(err).lower():
                return None
            raise

    def _misconfigured(self, spec):
        """Vrai si un conteneur SANS données tourne avec d'autres arguments
        que ceux attendus."""
        if not (spec.stateless and spec.image_cmd):
            return False
        cmd = self._docker(["inspect", "-f", "{{json .Config.Cmd}}",
                            spec.container], timeout=10)
        try:
            return json.loads(cmd) != spec.image_cmd
        except ValueError:
            return False

    def _ensure_restart_policy(self, spec):
        """Corrige un conteneur créé sans --restart (tes conteneurs actuels)
        SANS le recréer : indispensable pour ne pas perdre la base Nominatim."""
        policy = self._docker(["inspect", "-f",
                               "{{.HostConfig.RestartPolicy.Name}}",
                               spec.container], timeout=10)
        if policy != "unless-stopped":
            self._docker(["update", "--restart", "unless-stopped",
                          spec.container])
            print("[cartes] {} : redémarrage automatique activé".format(
                spec.container))

    def _create(self, spec):
        missing = [p for p in spec.required if not os.path.exists(p)]
        if missing:
            raise DockerError("fichier de données manquant : " + missing[0])
        try:
            self._docker(["image", "inspect", spec.image], timeout=10)
        except DockerError:
            raise DockerError("image {0} absente : la télécharger une fois avec "
                              "internet (docker pull {0})".format(spec.image))
        print("[cartes] création de {}".format(spec.container))
        self._docker(["run", "-d", "--name", spec.container,
                      "--restart", "unless-stopped"] + spec.run_args
                     + [spec.image] + spec.image_cmd, timeout=60)

    # --- état ---------------------------------------------------------------
    def _set(self, st, state, reason):
        with self._lock:
            changed = (st.state, st.reason) != (state, reason)
            if st.state != state:
                st.since = time.time()
            st.state, st.reason = state, reason
        if not changed:
            return
        if state == READY:
            print("[cartes] {} : prêt".format(st.spec.label))
        elif state == DOWN:
            print("[cartes] {} : INDISPONIBLE — {}".format(st.spec.label, reason))
        else:
            print("[cartes] {} : {}".format(st.spec.label, reason))
        snap = self.snapshot()
        for cb in list(self._listeners):
            try:
                cb(snap)
            except Exception as err:
                print("[cartes] erreur d'un abonné :", err)


_instance = None


def get_map_services():
    """Instance partagée (créée à la première demande)."""
    global _instance
    if _instance is None:
        _instance = MapServices()
    return _instance
