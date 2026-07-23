#!/usr/bin/env python3
"""Gestion de l'énergie : batterie (MCP3008 via SPI) et veille."""

from nova.utils.platform_utils import is_raspberry_pi

try:
    import spidev
except ImportError:
    spidev = None

# Bornes de tension d'une cellule Li-Po (après pont diviseur x2)
VOLT_EMPTY = 3.2
VOLT_FULL = 4.2
ADC_REF = 3.3
ADC_MAX = 1023.0
DIVIDER_RATIO = 2.0


class PowerManager:
    """Lit le niveau de batterie et expose les seuils d'économie d'énergie."""

    def __init__(self, low_threshold=15):
        self.low_threshold = low_threshold
        self.battery_voltage = 0.0
        self.battery_percent = 0.0
        self.spi = None
        self.simulated = True

        if spidev is not None and is_raspberry_pi():
            try:
                self.spi = spidev.SpiDev()
                self.spi.open(0, 0)
                self.spi.max_speed_hz = 1350000
                self.simulated = False
            except Exception as error:
                print("[power] MCP3008 indisponible ({}), mode simulation".format(error))
                self.spi = None

    def read_adc(self, channel=0):
        """Lit un canal du MCP3008 (0-1023)."""
        if self.spi is None:
            return 0
        raw = self.spi.xfer2([1, (8 + channel) << 4, 0])
        return ((raw[1] & 3) << 8) + raw[2]

    def get_battery_level(self):
        """Retourne le niveau de batterie en pourcentage (0-100)."""
        if self.simulated:
            self.battery_voltage = 3.9
            self.battery_percent = 76.0
            return self.battery_percent

        raw = self.read_adc(0)
        voltage = (raw * ADC_REF / ADC_MAX) * DIVIDER_RATIO
        self.battery_voltage = voltage
        percent = (voltage - VOLT_EMPTY) / (VOLT_FULL - VOLT_EMPTY) * 100.0
        self.battery_percent = max(0.0, min(100.0, percent))
        return self.battery_percent

    def is_low_battery(self):
        return self.get_battery_level() < self.low_threshold

    def cleanup(self):
        if self.spi is not None:
            try:
                self.spi.close()
            except Exception:
                pass
            self.spi = None


_instance = None


def get_power_manager():
    global _instance
    if _instance is None:
        _instance = PowerManager()
    return _instance
