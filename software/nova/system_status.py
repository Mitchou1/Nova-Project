#!/usr/bin/env python3
"""État RÉEL du système (WiFi, Bluetooth, batterie, stockage, température,
IP, version), lu depuis le Pi lui-même — pas depuis la config.

Pourquoi : l'app Paramètres affichait l'état stocké en configuration (et un
« CONNECTE — NOVA_NETWORK » codé en dur) ; si le WiFi était coupé ailleurs,
NOVA l'ignorait. Et une commande qui échouait (droits, service absent)
laissait quand même l'interrupteur dans le nouvel état.

Principes :
  - chaque valeur vient d'une commande ou d'un fichier système réel ;
  - une valeur illisible vaut None avec une « erreur » explicite, jamais
    une valeur inventée ;
  - basculer WiFi/Bluetooth vérifie le résultat, puis RELIT l'état ;
  - les commandes (jusqu'à quelques secondes) tournent dans un thread :
    l'interface lit seulement le dernier état connu (instantane()).

Toutes les commandes sont lancées avec LC_ALL=C : nmcli répond sinon dans
la langue du système (« oui/non » au lieu de « yes/no »), ce qui cassait
l'analyse.
"""

import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

_ENV_C = dict(os.environ, LC_ALL="C", LANG="C")


def lancer(cmd, timeout=4):
    """Exécute une commande : (code, sortie, erreur). code None = introuvable
    ou délai dépassé (le message est alors dans « erreur »)."""
    if shutil.which(cmd[0]) is None:
        return None, "", "commande « {} » introuvable".format(cmd[0])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_ENV_C)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return None, "", "« {} » ne répond pas (délai dépassé)".format(" ".join(cmd[:2]))
    except OSError as err:
        return None, "", str(err)


def _explique_nmcli(err):
    bas = (err or "").lower()
    if "not authorized" in bas or "insufficient privileges" in bas:
        return ("droits insuffisants (polkit) : NOVA doit tourner dans la "
                "session de l'utilisateur connecté")
    if "networkmanager is not running" in bas:
        return "NetworkManager est arrêté (sudo systemctl start NetworkManager)"
    lignes = (err or "").strip().splitlines()
    return lignes[-1][:120] if lignes else "erreur inconnue"


# ═════════════════════════════════════════════════════════════════════════
# WiFi (NetworkManager / nmcli)
# ═════════════════════════════════════════════════════════════════════════
def lire_wifi(run=lancer):
    etat = {"disponible": False, "actif": None, "ssid": None, "signal": None, "erreur": None}
    code, sortie, err = run(["nmcli", "-t", "-f", "WIFI", "radio"])
    if code != 0:
        etat["erreur"] = _explique_nmcli(err) if code is not None else err
        return etat
    etat["disponible"] = True
    etat["actif"] = sortie.strip().lower() == "enabled"
    if not etat["actif"]:
        return etat
    # --rescan no : lire l'état connu sans lancer un balayage radio (lent)
    code, sortie, _err = run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL",
                              "dev", "wifi", "list", "--rescan", "no"])
    if code == 0:
        for ligne in sortie.splitlines():
            # « : » dans un SSID est échappé en « \: » par nmcli -t
            champs = [c.replace("\\:", ":") for c in re.split(r"(?<!\\):", ligne)]
            if len(champs) >= 3 and champs[0] == "yes":
                etat["ssid"] = champs[1] or "(réseau masqué)"
                try:
                    etat["signal"] = int(champs[2])
                except ValueError:
                    pass
                break
    return etat


def basculer_wifi(actif, run=lancer):
    """Active/coupe le WiFi. (réussi, message d'erreur ou None)."""
    code, _s, err = run(["nmcli", "radio", "wifi", "on" if actif else "off"], timeout=8)
    if code == 0:
        return True, None
    return False, _explique_nmcli(err) if code is not None else err


# ═════════════════════════════════════════════════════════════════════════
# Bluetooth (BlueZ / bluetoothctl)
# ═════════════════════════════════════════════════════════════════════════
_BT_ARRETE = "service Bluetooth arrêté (sudo systemctl enable --now bluetooth)"


def _service_bluetooth_actif(run):
    code, sortie, _e = run(["systemctl", "is-active", "bluetooth"], timeout=3)
    if code is None:          # pas de systemd : on laisse bluetoothctl juger
        return True
    return sortie.strip() == "active"


def lire_bluetooth(run=lancer):
    etat = {"disponible": False, "actif": None, "appareils": [], "erreur": None}
    # Service arrêté : bluetoothctl attendrait bluetoothd indéfiniment
    if not _service_bluetooth_actif(run):
        etat["erreur"] = _BT_ARRETE
        return etat
    code, sortie, err = run(["bluetoothctl", "show"])
    if code is None:
        etat["erreur"] = err
        return etat
    if "No default controller" in sortie + err or "Powered:" not in sortie:
        etat["erreur"] = "aucun adaptateur Bluetooth détecté"
        return etat
    etat["disponible"] = True
    etat["actif"] = bool(re.search(r"Powered:\s*yes", sortie))
    # « devices Paired » (BlueZ récent), sinon « paired-devices » (ancien)
    code, sortie, err = run(["bluetoothctl", "devices", "Paired"])
    if code != 0 or "Invalid command" in sortie + err:
        code, sortie, err = run(["bluetoothctl", "paired-devices"])
    for ligne in sortie.splitlines():
        m = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s*(.*)", ligne.strip())
        if m:
            etat["appareils"].append(m.group(2).strip() or m.group(1))
    return etat


def basculer_bluetooth(actif, run=lancer):
    """Allume/éteint le Bluetooth. bluetoothctl renvoie souvent 0 même en
    cas d'échec : on analyse aussi sa sortie."""
    if not _service_bluetooth_actif(run):
        return False, _BT_ARRETE
    code, sortie, err = run(["bluetoothctl", "power", "on" if actif else "off"], timeout=8)
    texte = sortie + err
    if "Blocked" in texte or "rfkill" in texte.lower():
        return False, "Bluetooth bloqué par rfkill (sudo rfkill unblock bluetooth)"
    if "No default controller" in texte:
        return False, "aucun adaptateur Bluetooth détecté"
    if code is None:
        return False, err
    if code != 0 or "Failed" in texte:
        lignes = texte.strip().splitlines()
        return False, lignes[-1][:120] if lignes else "échec inconnu"
    return True, None


# ═════════════════════════════════════════════════════════════════════════
# Système : stockage, température, IP, version, alimentation
# ═════════════════════════════════════════════════════════════════════════
def lire_stockage(chemin="/"):
    try:
        u = shutil.disk_usage(chemin)
        return {"libre_go": u.free / 1e9, "total_go": u.total / 1e9}
    except OSError:
        return {"libre_go": None, "total_go": None}


def lire_temperature_cpu():
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000.0
    except (OSError, ValueError):
        return None


_INTERFACES_VIRTUELLES = ("lo", "docker", "br-", "virbr", "veth", "vnet", "tun", "tap")


def lire_ip(run=lancer):
    """Adresse de l'interface qui sort vraiment vers le réseau (route par
    défaut) : la 1re adresse listée pouvait être celle d'un pont virtuel
    (docker0, virbr0 de libvirt...) — observé sur le PC de développement."""
    code, sortie, _e = run(["ip", "-4", "route", "get", "192.0.2.1"])
    if code == 0:
        m = re.search(r"dev\s+(\S+).*?src\s+([\d.]+)", sortie)
        if m:
            return "{} ({})".format(m.group(2), m.group(1))
    code, sortie, _e = run(["ip", "-4", "-o", "addr", "show", "scope", "global"])
    if code == 0:
        for m in re.finditer(r"^\d+:\s+(\S+)\s+inet\s+([\d.]+)", sortie, re.M):
            if not m.group(1).startswith(_INTERFACES_VIRTUELLES):
                return "{} ({})".format(m.group(2), m.group(1))
    try:
        # Aucun paquet n'est envoyé : connect() en UDP choisit seulement
        # l'interface de sortie, ce qui donne l'adresse locale.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            ip = s.getsockname()[0]
            return None if ip.startswith("0.") else ip
    except OSError:
        return None


def lire_systeme():
    nom = platform.system()
    try:
        for ligne in Path("/etc/os-release").read_text().splitlines():
            if ligne.startswith("PRETTY_NAME="):
                nom = ligne.split("=", 1)[1].strip('"')
    except OSError:
        pass
    try:
        modele = Path("/proc/device-tree/model").read_text().strip("\x00\n ")
    except OSError:
        modele = "{} ({})".format(platform.node(), platform.machine())
    return {"systeme": "{} · noyau {}".format(nom, platform.release()), "modele": modele}


# Bits de « vcgencmd get_throttled » (firmware Raspberry Pi)
_BITS_ALIM = {0: "sous-tension en cours", 1: "fréquence plafonnée", 2: "ralenti",
              3: "limite de température", 16: "sous-tension depuis le démarrage",
              18: "ralenti depuis le démarrage"}


def lire_alimentation(run=lancer):
    """État de l'alimentation vu par le firmware du Pi. Utile avec un UPS :
    une sous-tension explique plantages et corruption de carte SD."""
    code, sortie, _err = run(["vcgencmd", "get_throttled"])
    if code != 0:
        return {"ok": None, "detail": "non disponible (vcgencmd absent : pas un Raspberry Pi)"}
    m = re.search(r"0x([0-9a-fA-F]+)", sortie)
    if not m:
        return {"ok": None, "detail": sortie.strip() or "réponse illisible"}
    valeur = int(m.group(1), 16)
    problemes = [txt for bit, txt in sorted(_BITS_ALIM.items()) if valeur & (1 << bit)]
    return {"ok": not problemes,
            "detail": "correcte" if not problemes else ", ".join(problemes)}


# ═════════════════════════════════════════════════════════════════════════
# État global, rafraîchi en arrière-plan
# ═════════════════════════════════════════════════════════════════════════
def lire_tout(run=lancer):
    """Lecture complète (bloquante : quelques secondes au pire)."""
    from nova.power_manager import get_power_manager
    etat = {
        "wifi": lire_wifi(run),
        "bluetooth": lire_bluetooth(run),
        "batterie": get_power_manager().statut(),
        "stockage": lire_stockage(),
        "cpu_temp": lire_temperature_cpu(),
        "ip": lire_ip(run),
        "alimentation": lire_alimentation(run),
        "horodatage": time.time(),
    }
    etat.update(lire_systeme())
    return etat


class Surveillance:
    """Relit l'état toutes les `intervalle` secondes dans un thread ; les
    écrans lisent instantane() sans jamais attendre une commande."""

    def __init__(self, lecteur=lire_tout, intervalle=30):
        self._lecteur = lecteur
        self.intervalle = intervalle
        self._etat = None
        self._verrou = threading.Lock()
        self._reveil = threading.Event()
        self._abonnes = []
        self._thread = None

    def instantane(self):
        with self._verrou:
            return self._etat

    def abonner(self, rappel):
        if rappel not in self._abonnes:
            self._abonnes.append(rappel)

    def desabonner(self, rappel):
        if rappel in self._abonnes:
            self._abonnes.remove(rappel)

    def demarrer(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._boucle, name="etat-systeme",
                                            daemon=True)
            self._thread.start()

    def rafraichir_maintenant(self):
        """Demande une relecture immédiate (sans attendre l'intervalle)."""
        self.demarrer()
        self._reveil.set()

    def rafraichir(self):
        """Relecture synchrone (à appeler hors du thread graphique)."""
        try:
            etat = self._lecteur()
        except Exception as err:          # ne jamais tuer la surveillance
            print("[systeme] lecture impossible :", err)
            return self.instantane()
        with self._verrou:
            self._etat = etat
        for rappel in list(self._abonnes):
            try:
                rappel(etat)
            except Exception as err:
                print("[systeme] erreur d'un abonné :", err)
        return etat

    def _boucle(self):
        while True:
            self.rafraichir()
            self._reveil.wait(self.intervalle)
            self._reveil.clear()


_surveillance = None


def surveillance():
    global _surveillance
    if _surveillance is None:
        _surveillance = Surveillance()
    return _surveillance
