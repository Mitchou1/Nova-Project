#!/usr/bin/env python3
"""Gestionnaire du serveur God's Eye View (globe 3D temps réel).

God's Eye View est une application web (Node.js + Vite + CesiumJS) installée
par scripts/install_gods_eye.sh dans external/gods-eye-view. Ce module la
démarre en arrière-plan (`npm run dev`), attend qu'elle réponde vraiment sur
son port, puis laisse l'appelant ouvrir le navigateur.

Choix assumés, à garder en tête :
  - C'est une EXCEPTION à la philosophie hors ligne de NOVA : vols, navires,
    satellites et imagerie viennent d'internet. Sans réseau, on ne démarre
    pas du tout (le globe serait vide et ferait croire à un bug).
  - Le serveur coûte de la RAM (Node ~300 Mo, puis Chromium + Cesium 1 à
    2 Go) : on ne le lance qu'à la demande et on l'arrête à la fermeture de
    NOVA (gods_eye.auto_stop_on_exit) ou via le bouton d'arrêt.
  - Instance unique : un verrou + un fichier PID. Le PID permet aussi
    d'arrêter un serveur laissé par une session NOVA précédente (plantage).
  - Écoute sur 127.0.0.1 seulement : le serveur Vite de développement n'est
    pas fait pour être exposé au réseau.

Les rappels (on_progress / on_ready / on_error) sont appelés depuis un
thread : côté Kivy, l'appelant doit les repasser par Clock.schedule_once.
"""

import os
import re
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from nova.paths import DATA_DIR, LOGS_DIR, ROOT_DIR

# États
ARRETE = "arrete"
DEMARRAGE = "demarrage"
PRET = "pret"

DEFAULTS = {
    "enabled": True,
    "install_path": str(ROOT_DIR / "external" / "gods-eye-view"),
    "port": 4173,
    "auto_stop_on_exit": True,
    "startup_timeout": 120,
    # Zoom du navigateur : l'interface est pensée pour un écran de bureau,
    # illisible à 1.0 sur le 5 pouces. 1.5 = texte lisible et boutons d'au
    # moins ~42 px ; ça ne tient en 800x480 QUE grâce à l'adaptation tactile
    # ci-dessous (un panneau à la fois). Sans elle, ne pas dépasser 1.25.
    "zoom": 1.5,
    # Adaptation tactile (software/nova/assets/gods_eye_tactile) : barre
    # d'onglets, un seul panneau à la fois, bouton Fermer.
    "tactile": True,
}

INSTALL_SCRIPT = ROOT_DIR / "scripts" / "install_gods_eye.sh"
LOCAL_NODE_DIR = ROOT_DIR / "external" / "node" / "bin"
PID_FILE = DATA_DIR / "gods_eye.pid"
LOG_FILE = LOGS_DIR / "gods_eye.log"
# Profil Chromium dédié : (1) les options de zoom ne s'appliquent qu'au
# PREMIER Chromium lancé — avec un profil à part, elles marchent même si un
# autre Chromium est déjà ouvert ; (2) on peut retrouver et fermer CETTE
# fenêtre à l'arrêt, sans toucher aux autres fenêtres du navigateur.
PROFIL_NAVIGATEUR = DATA_DIR / "gods_eye_navigateur"
# Extension Chromium qui réorganise l'interface pour l'écran tactile, sans
# toucher au code de l'outil (ses mises à jour par git pull restent possibles).
EXTENSION_TACTILE = Path(__file__).resolve().parent / "assets" / "gods_eye_tactile"

# Sous ce seuil de RAM disponible, on prévient (sans bloquer) que le globe
# risque de ramer ou que le système va swapper.
RAM_CONSEILLEE_MO = 1500
# Intervalle entre deux messages « toujours en démarrage » dans le terminal
PROGRESSION_INTERVALLE = 10


def _log(message):
    print("[gods_eye]", message)


def charger_config():
    """Section gods_eye de system.json, complétée par les valeurs par défaut."""
    try:
        from nova.utils.config_loader import get_config
        section = get_config().get("gods_eye", {}) or {}
    except Exception as error:
        _log("config illisible ({}), valeurs par défaut".format(error))
        section = {}
    config = dict(DEFAULTS)
    config.update(section)
    config["install_path"] = os.path.expanduser(str(config["install_path"]))
    return config


def _node_compatible(binaire):
    """L'outil exige Node >= 24.14 (<25) ou 26.x (champ « engines »)."""
    try:
        sortie = subprocess.run([str(binaire), "--version"], capture_output=True,
                                text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    m = re.match(r"v(\d+)\.(\d+)", sortie)
    if not m:
        return False
    majeur, mineur = int(m.group(1)), int(m.group(2))
    return (majeur == 24 and mineur >= 14) or majeur == 26


def trouver_node_bin_dir():
    """Dossier contenant node/npm compatibles : d'abord celui installé par le
    script dans external/node, sinon celui du système. None si aucun."""
    if _node_compatible(LOCAL_NODE_DIR / "node"):
        return LOCAL_NODE_DIR
    for dossier in os.environ.get("PATH", "").split(os.pathsep):
        candidat = Path(dossier) / "node"
        if candidat.is_file() and _node_compatible(candidat):
            return candidat.parent
    return None


def internet_disponible(timeout=4):
    """Vrai si on joint réellement le web (pas seulement le Wi-Fi local)."""
    for hote in ("services.arcgisonline.com", "github.com"):
        try:
            with socket.create_connection((hote, 443), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def port_ouvert(port, hote="127.0.0.1"):
    try:
        with socket.create_connection((hote, port), timeout=1):
            return True
    except OSError:
        return False


def serveur_repond(port):
    """Le serveur est prêt quand la page d'accueil répond (pas juste le port :
    Vite ouvre le port avant d'avoir fini de charger sa configuration)."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:{}/".format(port),
                                    timeout=3) as rep:
            return rep.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def ram_disponible_mo():
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for ligne in f:
                if ligne.startswith("MemAvailable:"):
                    return int(ligne.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return None


def _lire_pid():
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)          # existe toujours ?
        return pid
    except (OSError, ValueError):
        return None


def _fin_du_log(nb=6):
    try:
        lignes = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(l for l in lignes[-nb:] if l.strip())
    except OSError:
        return ""


class GodsEyeManager:
    """Démarre / surveille / arrête le serveur God's Eye View."""

    def __init__(self):
        self._verrou = threading.Lock()
        self._proc = None
        self._etat = ARRETE
        self.url = None

    @property
    def etat(self):
        return self._etat

    def est_actif(self):
        return self._etat == PRET

    # ------------------------------------------------------------------
    # Démarrage
    # ------------------------------------------------------------------
    def demarrer(self, on_progress=None, on_ready=None, on_error=None):
        """Lance le serveur dans un thread. Renvoie False (et rappelle
        on_error) si un démarrage est déjà en cours."""
        def progres(msg):
            _log(msg)
            if on_progress:
                on_progress(msg)

        def erreur(msg):
            _log("échec : " + msg.replace("\n", " | "))
            if on_error:
                on_error(msg)

        with self._verrou:
            if self._etat == DEMARRAGE:
                erreur("un démarrage est déjà en cours, patiente.")
                return False
            self._etat = DEMARRAGE
        threading.Thread(target=self._demarrer_thread,
                         args=(progres, on_ready, erreur),
                         name="gods-eye-start", daemon=True).start()
        return True

    def _demarrer_thread(self, progres, on_ready, erreur):
        try:
            resultat = self._demarrer(progres)
        except Exception as error:      # filet de sécurité : jamais d'état figé
            resultat = "erreur inattendue : {}".format(error)
        if isinstance(resultat, str):
            self._etat = ARRETE
            erreur(resultat)
        else:
            self._etat = PRET
            if on_ready:
                on_ready(self.url)

    def _demarrer(self, progres):
        """Renvoie True si prêt, sinon le message d'échec (str)."""
        cfg = charger_config()
        port = int(cfg["port"])
        self.url = "http://localhost:{}".format(port)
        dossier = Path(cfg["install_path"])

        if not cfg.get("enabled", True):
            return "désactivé dans config/system.json (gods_eye.enabled)."

        # Déjà lancé (par nous, ou par une session NOVA précédente) ?
        pid = _lire_pid()
        if (self._proc and self._proc.poll() is None) or pid:
            if serveur_repond(port):
                progres("Serveur déjà en marche sur le port {}.".format(port))
                return True
            # Serveur bloqué ou orphelin qui ne répond plus : on le remplace
            # (sinon on en lancerait un second à côté)
            progres("Ancien serveur muet : arrêt avant relance.")
            self.arreter()
            self._etat = DEMARRAGE

        # Installation présente ?
        if not (dossier / "package.json").is_file():
            return ("installation manquante ({}).\nLance d'abord : {}"
                    .format(dossier, INSTALL_SCRIPT))
        if not (dossier / "node_modules").is_dir():
            return ("dépendances npm absentes dans {}.\nRelance : {}"
                    .format(dossier, INSTALL_SCRIPT))

        bin_dir = trouver_node_bin_dir()
        if bin_dir is None:
            return ("Node.js 24 introuvable (ni external/node ni système).\n"
                    "Relance : {}".format(INSTALL_SCRIPT))

        # Port pris par autre chose que nous : on ne peut pas démarrer
        if port_ouvert(port):
            return ("le port {} est déjà occupé par un autre programme.\n"
                    "Libère-le (ss -ltnp | grep {}) ou change gods_eye.port "
                    "dans config/system.json.".format(port, port))

        progres("Vérification de la connexion internet…")
        if not internet_disponible():
            return ("pas de connexion internet. God's Eye View ne fonctionne "
                    "qu'en ligne (vols, satellites, imagerie) : le globe "
                    "resterait vide.")

        ram = ram_disponible_mo()
        if ram is not None and ram < RAM_CONSEILLEE_MO:
            progres("Attention : seulement {} Mo de RAM libre. Le globe 3D en "
                    "demande 1 à 2 Go : attends-toi à de fortes lenteurs.".format(ram))

        progres("Démarrage du serveur (Node {}) sur le port {}…".format(
            "local" if bin_dir == LOCAL_NODE_DIR else "système", port))
        env = dict(os.environ)
        env["PATH"] = "{}{}{}".format(bin_dir, os.pathsep, env.get("PATH", ""))
        env["PORT"] = str(port)
        env["HOST"] = "127.0.0.1"
        env["BROWSER"] = "none"          # c'est NOVA qui ouvre le navigateur
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            journal = open(LOG_FILE, "w", encoding="utf-8")
            # Nouvelle session = nouveau groupe de processus : npm lance un
            # shell qui lance vite ; tuer le seul PID de npm laisserait vite
            # tourner (et garder la RAM). On tuera tout le groupe.
            self._proc = subprocess.Popen(
                [str(bin_dir / "npm"), "run", "dev", "--", "--strictPort"],
                cwd=str(dossier), env=env, stdout=journal,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                start_new_session=True)
            journal.close()             # le processus garde sa copie
        except OSError as error:
            return "lancement impossible : {}".format(error)
        try:
            PID_FILE.write_text(str(self._proc.pid))
        except OSError as error:
            _log("PID non enregistré : {}".format(error))

        # Attente : le premier démarrage sur le Pi est lent (Vite prépare
        # Cesium, plusieurs dizaines de secondes).
        delai = int(cfg.get("startup_timeout", 120))
        debut = time.monotonic()
        dernier_message = debut
        while True:
            if self._proc.poll() is not None:
                code = self._proc.returncode
                self._nettoyer_pid()
                self._proc = None
                return ("le serveur s'est arrêté (code {}). Fin du journal "
                        "{} :\n{}".format(code, LOG_FILE, _fin_du_log()))
            if serveur_repond(port):
                progres("Serveur prêt en {} s.".format(int(time.monotonic() - debut)))
                return True
            maintenant = time.monotonic()
            if maintenant - debut > delai:
                self.arreter()
                return ("pas de réponse après {} s (gods_eye.startup_timeout). "
                        "Le Pi est peut-être saturé. Journal : {}\n{}"
                        .format(delai, LOG_FILE, _fin_du_log()))
            if maintenant - dernier_message >= PROGRESSION_INTERVALLE:
                dernier_message = maintenant
                progres("… toujours en démarrage ({} s / {} s max)".format(
                    int(maintenant - debut), delai))
            time.sleep(1)

    # ------------------------------------------------------------------
    # Arrêt
    # ------------------------------------------------------------------
    @staticmethod
    def _tuer_groupe(pid, attente=5, proc=None):
        """SIGTERM au groupe entier (npm + vite), puis SIGKILL si besoin.

        `proc` (notre Popen) doit être « récolté » à chaque tour : sinon npm
        reste zombie, le groupe semble vivant et on attendait 10 s pour rien."""
        try:
            pgid = os.getpgid(pid)
        except OSError:
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pgid, sig)
            except OSError:
                return
            fin = time.monotonic() + attente
            while time.monotonic() < fin:
                if proc is not None:
                    proc.poll()
                try:
                    os.killpg(pgid, 0)
                except OSError:
                    return          # plus aucun processus dans le groupe
                time.sleep(0.2)

    def _nettoyer_pid(self):
        try:
            PID_FILE.unlink()
        except OSError:
            pass

    def arreter(self):
        """Arrête le serveur (le nôtre ou un orphelin d'une session
        précédente) pour libérer la RAM. Renvoie True si quelque chose
        tournait."""
        arrete = False
        proc = self._proc
        if proc is not None and proc.poll() is None:
            self._tuer_groupe(proc.pid, proc=proc)
            arrete = True
        else:
            pid = _lire_pid()
            if pid:
                self._tuer_groupe(pid)
                arrete = True
        self._proc = None
        self._nettoyer_pid()
        self._etat = ARRETE
        # Sans serveur, la fenêtre du globe ne sert plus à rien : on la ferme
        # aussi (elle seule garde 1 à 2 Go de RAM).
        fermer_navigateur()
        if arrete:
            _log("serveur arrêté, mémoire libérée.")
        return arrete

    def en_marche(self):
        """Vrai si un serveur tourne (lancé par cette session ou une autre)."""
        if self._proc is not None and self._proc.poll() is None:
            return True
        return _lire_pid() is not None

    def a_la_fermeture(self):
        """Appelé par NOVA à la fermeture (main.on_stop)."""
        if charger_config().get("auto_stop_on_exit", True):
            self.arreter()


def ouvrir_navigateur(url):
    """Ouvre l'URL ; Chromium en mode application (sans onglets ni barre
    d'adresse) pour gagner de la place sur l'écran 800x480, agrandi selon
    gods_eye.zoom, avec le pincement à deux doigts activé pour grossir un
    détail sans déformer la mise en page. Renvoie un message d'erreur, ou
    None si c'est ouvert."""
    import shutil
    try:
        zoom = float(charger_config().get("zoom", DEFAULTS["zoom"]))
    except (TypeError, ValueError):
        zoom = DEFAULTS["zoom"]
    zoom = min(max(zoom, 0.5), 3.0)       # garde-fou contre une faute de frappe
    # Sans l'adaptation tactile : fenêtre maximisée, dont la barre de titre
    # garde un bouton de fermeture. Avec : plein écran (les 480 px de haut
    # sont tous utiles), c'est l'onglet « Fermer » de l'extension qui ferme.
    options = ["--start-maximized"]
    if charger_config().get("tactile", True) and EXTENSION_TACTILE.is_dir():
        options = [
            "--start-fullscreen",
            "--load-extension={}".format(EXTENSION_TACTILE),
            # Chromium récent ignore --load-extension tant que cette
            # protection est active.
            "--disable-features=DisableLoadExtensionCommandLineSwitch",
        ]
    for nom in ("chromium", "chromium-browser"):
        binaire = shutil.which(nom)
        if binaire:
            try:
                subprocess.Popen([binaire, "--app={}".format(url),
                                  "--user-data-dir={}".format(PROFIL_NAVIGATEUR),
                                  "--force-device-scale-factor={}".format(zoom),
                                  "--enable-pinch", "--no-first-run",
                                  "--no-default-browser-check"] + options,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return None
            except OSError as error:
                _log("chromium non lancé : {}".format(error))
    import webbrowser
    try:
        if webbrowser.open(url):
            return None
    except Exception as error:
        _log("navigateur non lancé : {}".format(error))
    return "aucun navigateur n'a pu être ouvert (ouvre {} à la main).".format(url)


def fermer_navigateur():
    """Ferme la fenêtre du globe (et elle seule : repérée par son profil)."""
    motif = "--user-data-dir={}".format(PROFIL_NAVIGATEUR)
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open("/proc/{}/cmdline".format(pid), "rb") as f:
                    ligne = f.read().decode("utf-8", "replace").replace("\0", " ")
            except OSError:
                continue
            # Chromium réécrit sa ligne de commande en UNE chaîne (arguments
            # séparés par des espaces, pas par \0) : on cherche donc une
            # sous-chaîne. Seul le processus principal (sans --type=) est
            # visé : le fermer ferme proprement tous ses sous-processus.
            if (ligne.split(" ", 1)[0].endswith("/chromium")
                    and (motif + " ") in (ligne + " ")
                    and "--type=" not in ligne):
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except OSError:
                    pass
    except OSError as error:
        _log("fermeture du navigateur impossible : {}".format(error))


_manager = None


def get_gods_eye():
    """Instance partagée : garantit un seul serveur pour toute l'application."""
    global _manager
    if _manager is None:
        _manager = GodsEyeManager()
    return _manager
