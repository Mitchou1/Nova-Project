#!/usr/bin/env python3
"""Tests de l'état système réel et de la lecture de l'UPS, sans matériel :
les commandes (nmcli, bluetoothctl...) et le bus I2C sont simulés.
"""

import sys
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova import power_manager as pm
from nova import system_status as ss


def faux_run(reponses):
    """reponses : {"commande jointe": (code, sortie, erreur)}."""
    appels = []

    def run(cmd, timeout=4):
        cle = " ".join(cmd)
        appels.append(cle)
        return reponses.get(cle, (None, "", "commande « {} » introuvable".format(cmd[0])))
    run.appels = appels
    return run


# ─── WiFi ───────────────────────────────────────────────────────────────
LISTE_WIFI = "no:Voisin:40\nyes:Maison\\:5G:78\nno:Autre:20\n"


def test_wifi_connecte_ssid_avec_deux_points_et_signal():
    run = faux_run({"nmcli -t -f WIFI radio": (0, "enabled\n", ""),
                    "nmcli -t -f ACTIVE,SSID,SIGNAL dev wifi list --rescan no": (0, LISTE_WIFI, "")})
    assert ss.lire_wifi(run) == {"disponible": True, "actif": True, "ssid": "Maison:5G",
                                 "signal": 78, "erreur": None}


def test_wifi_desactive():
    etat = ss.lire_wifi(faux_run({"nmcli -t -f WIFI radio": (0, "disabled\n", "")}))
    assert etat["actif"] is False and etat["ssid"] is None


def test_wifi_nmcli_absent_le_dit():
    etat = ss.lire_wifi(faux_run({}))
    assert etat["disponible"] is False and "nmcli" in etat["erreur"]


def test_bascule_wifi_refusee_explique_polkit():
    run = faux_run({"nmcli radio wifi off": (1, "", "Error: Not authorized to control networking.")})
    reussi, erreur = ss.basculer_wifi(False, run)
    assert not reussi and "polkit" in erreur


def test_bascule_wifi_ok():
    assert ss.basculer_wifi(True, faux_run({"nmcli radio wifi on": (0, "", "")})) == (True, None)


# ─── Bluetooth ──────────────────────────────────────────────────────────
BT_SHOW = "Controller AA:BB:CC:DD:EE:FF (public)\n\tName: nova\n\tPowered: yes\n"


def test_bluetooth_service_arrete_sans_appeler_bluetoothctl():
    run = faux_run({"systemctl is-active bluetooth": (3, "inactive\n", "")})
    etat = ss.lire_bluetooth(run)
    assert "service Bluetooth arrêté" in etat["erreur"]
    assert not any(a.startswith("bluetoothctl") for a in run.appels)   # pas de blocage


def test_bluetooth_actif_avec_appareils():
    run = faux_run({"systemctl is-active bluetooth": (0, "active\n", ""),
                    "bluetoothctl show": (0, BT_SHOW, ""),
                    "bluetoothctl devices Paired": (0, "Device 11:22:33:44:55:66 Casque JBL\n", "")})
    etat = ss.lire_bluetooth(run)
    assert etat["actif"] is True and etat["appareils"] == ["Casque JBL"]


def test_bluetooth_ancien_bluez_paired_devices():
    run = faux_run({"systemctl is-active bluetooth": (0, "active\n", ""),
                    "bluetoothctl show": (0, BT_SHOW.replace("yes", "no"), ""),
                    "bluetoothctl devices Paired": (0, "Invalid command\n", ""),
                    "bluetoothctl paired-devices": (0, "Device 11:22:33:44:55:66 Montre\n", "")})
    etat = ss.lire_bluetooth(run)
    assert etat["actif"] is False and etat["appareils"] == ["Montre"]


def test_bluetooth_sans_adaptateur():
    run = faux_run({"systemctl is-active bluetooth": (0, "active\n", ""),
                    "bluetoothctl show": (0, "No default controller available\n", "")})
    assert ss.lire_bluetooth(run)["erreur"] == "aucun adaptateur Bluetooth détecté"


def test_bascule_bluetooth_bloque_rfkill_malgre_code_0():
    run = faux_run({"systemctl is-active bluetooth": (0, "active\n", ""),
                    "bluetoothctl power on": (0, "Failed to set power on: org.bluez.Error.Blocked\n", "")})
    reussi, erreur = ss.basculer_bluetooth(True, run)
    assert not reussi and "rfkill unblock" in erreur


# ─── adresse IP ─────────────────────────────────────────────────────────
def test_ip_de_la_route_par_defaut():
    run = faux_run({"ip -4 route get 192.0.2.1":
                    (0, "192.0.2.1 via 192.168.1.1 dev wlan0 src 192.168.1.42 uid 1000\n", "")})
    assert ss.lire_ip(run) == "192.168.1.42 (wlan0)"


def test_ip_ignore_les_ponts_virtuels_sans_route():
    run = faux_run({"ip -4 route get 192.0.2.1": (2, "", "RTNETLINK answers: Network is unreachable"),
                    "ip -4 -o addr show scope global": (0,
                        "4: virbr0    inet 192.168.122.1/24 brd x scope global virbr0\n"
                        "3: wlan0    inet 10.0.0.7/24 brd x scope global wlan0\n", "")})
    assert ss.lire_ip(run) == "10.0.0.7 (wlan0)"


# ─── alimentation (firmware du Pi) ──────────────────────────────────────
def test_alimentation_sous_tension_depuis_demarrage():
    run = faux_run({"vcgencmd get_throttled": (0, "throttled=0x50000\n", "")})
    etat = ss.lire_alimentation(run)
    assert etat["ok"] is False and "sous-tension depuis le démarrage" in etat["detail"]


def test_alimentation_correcte():
    run = faux_run({"vcgencmd get_throttled": (0, "throttled=0x0\n", "")})
    assert ss.lire_alimentation(run) == {"ok": True, "detail": "correcte"}


# ─── surveillance ───────────────────────────────────────────────────────
def test_surveillance_notifie_et_survit_aux_erreurs():
    vus = []
    s = ss.Surveillance(lecteur=lambda: {"x": 1})
    s.abonner(vus.append)
    assert s.rafraichir() == {"x": 1} and vus == [{"x": 1}]
    s._lecteur = lambda: 1 / 0
    assert s.rafraichir() == {"x": 1}          # garde le dernier état connu


# ─── UPS I2C ────────────────────────────────────────────────────────────
class FauxBus:
    """Registres big-endian ; smbus renvoie les mots en little-endian."""

    def __init__(self, mots=None, blocs=None):
        self.mots, self.blocs = mots or {}, blocs or {}

    def read_word_data(self, adresse, registre):
        if (adresse, registre) not in self.mots:
            raise OSError(121, "Remote I/O error")
        v = self.mots[(adresse, registre)]
        return ((v & 0xFF) << 8) | (v >> 8)

    def read_i2c_block_data(self, adresse, registre, n):
        if (adresse, registre) not in self.blocs:
            raise OSError(121, "Remote I/O error")
        return self.blocs[(adresse, registre)][:n]


def _pm(bus):
    return pm.PowerManager(bus=bus)


def test_ina219_ups_hat_b_2_elements_en_charge():
    # 7,8 V (7800 mV / 4 mV = 1950, décalé de 3 bits), shunt positif
    bus = FauxBus(mots={(0x42, 0x02): 1950 << 3, (0x42, 0x01): 120})
    st = _pm(bus).statut()
    assert not st["simule"] and st["source"] == "INA219 0x42"
    assert abs(st["tension"] - 7.8) < 0.01 and abs(st["pourcent"] - 75.0) < 0.5
    assert st["en_charge"] is True


def test_max17040_geekworm():
    # VCELL 4,0 V -> 3200 pas de 1,25 mV (<<4) ; SOC 87 %
    bus = FauxBus(mots={(0x36, 0x02): 3200 << 4, (0x36, 0x04): 87 << 8})
    st = _pm(bus).statut()
    assert st["source"] == "MAX17040 0x36" and st["pourcent"] == 87.0


def test_ups_hat_e():
    # 8,2 V (8200 mV), courant +500 mA, 64 %, charge en cours (bit 0x40)
    blocs = {(0x2D, 0x20): [0x08, 0x20, 0xF4, 0x01, 64, 0], (0x2D, 0x02): [0x40]}
    st = _pm(FauxBus(blocs=blocs)).statut()
    assert st["source"] == "UPS HAT (E) 0x2d" and st["pourcent"] == 64.0
    assert st["en_charge"] is True


def test_autre_puce_en_0x40_pas_prise_pour_un_ups():
    # Capteur quelconque en 0x40 : tension incohérente -> rejeté
    bus = FauxBus(mots={(0x40, 0x02): 0x0010, (0x40, 0x01): 0})
    st = _pm(bus).statut()
    assert st["simule"] and "aucun UPS" in st["raison"]


def test_sans_ups_simulation_annoncee_et_pas_de_mode_economie():
    pm_ = _pm(FauxBus())
    pm_.low_threshold = 90                 # 76 % simulés < 90 %...
    assert pm_.statut()["simule"] is True
    assert pm_.is_low_battery() is False   # ...mais une valeur simulée ne compte pas


def test_ups_reel_bas_declenche_le_mode_economie():
    bus = FauxBus(mots={(0x42, 0x02): 1540 << 3, (0x42, 0x01): 0})   # 6,16 V ≈ 7 %
    assert _pm(bus).is_low_battery() is True


def test_assistant_batterie_simulee_le_dit(monkeypatch):
    from nova import assistant_actions as aa
    monkeypatch.setattr(pm, "_instance", _pm(FauxBus()))
    reponse = aa.execute_action({"action": "batterie"})
    assert "pas de mesure réelle" in reponse and "simulée" in reponse


def test_assistant_batterie_reelle(monkeypatch):
    from nova import assistant_actions as aa
    bus = FauxBus(mots={(0x42, 0x02): 1950 << 3, (0x42, 0x01): 120})
    monkeypatch.setattr(pm, "_instance", _pm(bus))
    assert aa.execute_action({"action": "batterie"}) == "Batterie à 75 %, en charge."
