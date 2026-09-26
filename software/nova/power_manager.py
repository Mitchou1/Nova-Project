#!/usr/bin/env python3
"""Gestion de l'énergie : batterie (UPS HAT en I2C) et mode économie.

Détection automatique de l'UPS sur le bus I2C 1, par ordre :
  - 0x2d        Waveshare UPS HAT (E)          (registres propriétaires)
  - 0x36        jauge MAX17040 / MAX17048       (Geekworm X120x, etc.)
  - 0x42 0x43 0x41 0x40  INA219                 (Waveshare UPS HAT B / C / D)
Chaque lecture est contrôlée (tension plausible) : une autre puce à la
même adresse (ex. un capteur en 0x40) n'est jamais prise pour un UPS.

Honnêteté : sans UPS lisible, l'état est SIMULÉ et le dit (statut()
explique pourquoi). Une valeur simulée ne déclenche jamais le mode
économie d'énergie. Avant, un MCP3008 (SPI) était lu d'office : sur un Pi
où le SPI est activé sans MCP3008 branché, il lisait 0 V -> 0 % de
batterie -> mode économie déclenché à tort. Il n'est plus utilisé que si
la config le demande ("battery": {"source": "mcp3008"}).
"""

import threading
import time

from nova.utils.platform_utils import is_raspberry_pi

try:
    import smbus2
except ImportError:
    smbus2 = None

try:
    import spidev
except ImportError:
    spidev = None

BUS_I2C = 1
REDETECTION = 60          # s : nouvelle tentative de détection si aucun UPS
POURCENT_SIMULE = 76.0

# MCP3008 (ancien montage, sur demande seulement)
VOLT_EMPTY = 3.2
VOLT_FULL = 4.2
ADC_REF = 3.3
ADC_MAX = 1023.0
DIVIDER_RATIO = 2.0


def _borne(v):
    return max(0.0, min(100.0, v))


def _mot_be(bus, adresse, registre):
    """Mot de 16 bits big-endian (smbus lit en little-endian)."""
    brut = bus.read_word_data(adresse, registre)
    return ((brut & 0xFF) << 8) | (brut >> 8)


# ─── lecteurs par puce : dict de mesures, ou None si non plausible ───────
def lire_ups_e(bus, adresse=0x2D):
    """Waveshare UPS HAT (E), d'après le programme d'exemple Waveshare :
    0x02 = état de charge, 0x20.. = tension (mV), courant (mA), pourcentage.
    (Registres non vérifiables sur ce poste : à valider sur le Pi.)"""
    d = bus.read_i2c_block_data(adresse, 0x20, 6)
    tension = (d[0] | d[1] << 8) / 1000.0
    pourcent = d[4] | d[5] << 8
    if not (5.0 <= tension <= 17.5 and 0 <= pourcent <= 100):
        return None
    charge = bus.read_i2c_block_data(adresse, 0x02, 1)[0]
    return {"pourcent": float(pourcent), "tension": tension,
            "en_charge": bool(charge & 0xC0), "puce": "UPS HAT (E)"}


def lire_max17040(bus, adresse=0x36):
    """Jauge MAX17040/17048 : pourcentage calculé par la puce elle-même."""
    vcell = _mot_be(bus, adresse, 0x02)
    pourcent = _mot_be(bus, adresse, 0x04) / 256.0
    # MAX17040 : 1,25 mV par pas sur 12 bits ; MAX17048 : 78,125 µV par pas
    for tension, nom in (((vcell >> 4) * 0.00125, "MAX17040"), (vcell * 78.125e-6, "MAX17048")):
        if 2.5 <= tension <= 4.5 and 0 <= pourcent <= 105:
            return {"pourcent": _borne(pourcent), "tension": tension,
                    "en_charge": None, "puce": nom}
    return None


def lire_ina219(bus, adresse):
    """INA219 (Waveshare UPS HAT B/C/D) : tension du pack ; le pourcentage
    est estimé depuis la tension, comme dans le programme Waveshare."""
    tension = (_mot_be(bus, adresse, 0x02) >> 3) * 0.004
    if 5.0 <= tension <= 8.6:          # 2 éléments en série (UPS HAT B)
        pourcent = (tension - 6.0) / 2.4 * 100
    elif 2.8 <= tension <= 4.35:       # 1 élément (UPS HAT C)
        pourcent = (tension - 3.0) / 1.2 * 100
    else:
        return None
    shunt = _mot_be(bus, adresse, 0x01)
    if shunt > 0x7FFF:
        shunt -= 0x10000
    # Convention Waveshare : courant positif = la batterie se charge
    return {"pourcent": _borne(pourcent), "tension": tension,
            "en_charge": shunt > 0, "puce": "INA219"}


CANDIDATS = [(0x2D, lire_ups_e), (0x36, lire_max17040)] + \
    [(a, lire_ina219) for a in (0x42, 0x43, 0x41, 0x40)]


def detecter_ups(bus):
    """(adresse, lecteur, mesure) du premier UPS plausible, ou None."""
    for adresse, lecteur in CANDIDATS:
        try:
            mesure = lecteur(bus, adresse)
        except OSError:
            continue                    # rien à cette adresse
        if mesure is not None:
            return adresse, lecteur, mesure
    return None


class PowerManager:
    def __init__(self, low_threshold=15, bus=None):
        self.low_threshold = low_threshold
        self.battery_voltage = 0.0
        self.battery_percent = POURCENT_SIMULE
        self.simulated = True
        self.charging = None
        self.source = "simulation"
        self.raison = "détection en cours"
        self.spi = None
        self._bus = bus
        self._ups = None                  # (adresse, lecteur)
        self._derniere_detection = 0.0
        # Lue à la fois par l'interface (thread Kivy) et par la surveillance
        # système (autre thread) : deux lectures I2C ne doivent pas se mêler.
        self._verrou = threading.RLock()
        if self._lire_source_config() == "mcp3008":
            self._ouvrir_mcp3008()

    @staticmethod
    def _lire_source_config():
        try:
            from nova.utils.config_loader import get_config
            return ((get_config().get("battery", {}) or {}).get("source") or "auto").lower()
        except Exception:
            return "auto"

    # --- MCP3008 (ancien montage) -----------------------------------------
    def _ouvrir_mcp3008(self):
        if spidev is None or not is_raspberry_pi():
            self.raison = "MCP3008 demandé mais spidev indisponible"
            return
        try:
            self.spi = spidev.SpiDev()
            self.spi.open(0, 0)
            self.spi.max_speed_hz = 1350000
        except Exception as error:
            self.raison = "MCP3008 indisponible ({})".format(error)
            self.spi = None

    def read_adc(self, channel=0):
        if self.spi is None:
            return 0
        raw = self.spi.xfer2([1, (8 + channel) << 4, 0])
        return ((raw[1] & 3) << 8) + raw[2]

    # --- UPS I2C ----------------------------------------------------------
    def _ouvrir_bus(self):
        if self._bus is not None:
            return self._bus
        if smbus2 is None:
            self.raison = "module smbus2 absent (pip install smbus2)"
            return None
        try:
            self._bus = smbus2.SMBus(BUS_I2C)
        except (OSError, FileNotFoundError) as err:
            self.raison = ("bus I2C indisponible ({}) : activer I2C dans "
                           "raspi-config".format(err))
            return None
        return self._bus

    def _mesurer(self):
        """Lit la batterie ; renvoie une mesure réelle ou None."""
        if self.spi is not None:
            volts = (self.read_adc(0) * ADC_REF / ADC_MAX) * DIVIDER_RATIO
            return {"pourcent": _borne((volts - VOLT_EMPTY) / (VOLT_FULL - VOLT_EMPTY) * 100),
                    "tension": volts, "en_charge": None, "puce": "MCP3008"}
        bus = self._ouvrir_bus()
        if bus is None:
            return None
        if self._ups is not None:
            adresse, lecteur = self._ups
            try:
                mesure = lecteur(bus, adresse)
                if mesure is not None:
                    return dict(mesure, adresse=adresse)
            except OSError as err:
                print("[power] UPS 0x{:02x} ne répond plus : {}".format(adresse, err))
            self._ups = None
        # Pas d'UPS connu : nouvelle détection au plus une fois par minute
        if self._derniere_detection and time.time() - self._derniere_detection < REDETECTION:
            return None
        self._derniere_detection = time.time()
        trouve = detecter_ups(bus)
        if trouve is None:
            self.raison = ("aucun UPS reconnu sur le bus I2C (adresses testées : "
                           "0x2d, 0x36, 0x40 à 0x43)")
            return None
        adresse, lecteur, mesure = trouve
        self._ups = (adresse, lecteur)
        print("[power] UPS détecté : {} en 0x{:02x}".format(mesure["puce"], adresse))
        return dict(mesure, adresse=adresse)

    def get_battery_level(self):
        with self._verrou:
            return self._lire_niveau()

    def _lire_niveau(self):
        mesure = None
        try:
            mesure = self._mesurer()
        except Exception as err:
            self.raison = "lecture impossible ({})".format(err)
        if mesure is None:
            self.simulated = True
            self.source = "simulation"
            self.battery_percent = POURCENT_SIMULE
            self.battery_voltage = 0.0
            self.charging = None
            return self.battery_percent
        self.simulated = False
        self.raison = ""
        self.battery_percent = mesure["pourcent"]
        self.battery_voltage = mesure["tension"]
        self.charging = mesure.get("en_charge")
        self.source = mesure["puce"] + (" 0x{:02x}".format(mesure["adresse"])
                                        if "adresse" in mesure else "")
        return self.battery_percent

    def statut(self):
        """État complet pour l'interface (lit la batterie)."""
        with self._verrou:
            pourcent = self._lire_niveau()
            return {"pourcent": pourcent, "tension": self.battery_voltage or None,
                    "en_charge": self.charging, "simule": self.simulated,
                    "source": self.source, "raison": self.raison}

    def is_low_battery(self):
        niveau = self.get_battery_level()
        # Une valeur simulée ne doit jamais couper les animations de l'UI
        return (not self.simulated) and niveau < self.low_threshold

    def cleanup(self):
        if self.spi is not None:
            try:
                self.spi.close()
            except Exception:
                pass
            self.spi = None
        if self._bus is not None and hasattr(self._bus, "close"):
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None


_instance = None


def get_power_manager():
    global _instance
    if _instance is None:
        _instance = PowerManager()
    return _instance


# ---------------------------------------------------------------------------
# Mode economie d'energie (cahier des charges, Phase 10) : is_low_battery()
# existait deja mais n'etait jamais interroge par personne. L'UI (animations,
# particules) consulte ce drapeau via is_low_power_active() plutot que de
# relire directement la batterie a chaque frame.
# ---------------------------------------------------------------------------
_low_power_active = False


def is_low_power_active():
    return _low_power_active


def set_low_power_active(value):
    global _low_power_active
    _low_power_active = bool(value)


def refresh_low_power_state():
    """A appeler periodiquement (Clock) : met a jour le drapeau depuis la
    batterie reelle et renvoie True si l'etat vient de changer."""
    actif = get_power_manager().is_low_battery()
    change = actif != _low_power_active
    set_low_power_active(actif)
    return change
