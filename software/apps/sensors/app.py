#!/usr/bin/env python3
"""Application Capteurs — MPU-6050 (I2C) avec repli en simulation."""

from kivy.clock import Clock
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager
from nova.utils.platform_utils import is_raspberry_pi

try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None

MPU_ADDR = 0x68
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H = 0x43
ACCEL_SCALE = 16384.0   # LSB/g   (plage +-2 g)
GYRO_SCALE = 131.0      # LSB/dps (plage +-250 dps)


class SensorsApp(BaseApp):
    app_name = "Capteurs"
    app_icon = "📡"
    app_id = "sensors"

    def __init__(self, **kwargs):
        self.bus = None
        self.available = False
        super().__init__(**kwargs)
        self.init_bus()
        self._clock = Clock.schedule_interval(self.update_sensors, 0.5)

    def build_ui(self):
        super().build_ui()

        grid = GridLayout(cols=2, spacing=10, padding=8)
        self.labels = {}
        for key, title in (("accel", "Accelerometre"), ("gyro", "Gyroscope"),
                           ("env", "Environnement"), ("status", "Etat")):
            label = Label(text="{}\n--".format(title), font_size=15, halign="center")
            label.bind(size=lambda w, _v: setattr(w, "text_size", w.size))
            self.labels[key] = label
            grid.add_widget(label)

        self.content.add_widget(grid)

    def init_bus(self):
        if SMBus is None or not is_raspberry_pi():
            self.available = False
            return
        try:
            self.bus = SMBus(1)
            self.bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)
            self.available = True
        except Exception as error:
            print("[capteurs] MPU-6050 indisponible : {}".format(error))
            self.available = False

    def read_word(self, register):
        high = self.bus.read_byte_data(MPU_ADDR, register)
        low = self.bus.read_byte_data(MPU_ADDR, register + 1)
        value = (high << 8) + low
        return value - 65536 if value >= 0x8000 else value

    def update_sensors(self, dt=None):
        if not self.available:
            self.labels["accel"].text = "Accelerometre\n(simulation)"
            self.labels["gyro"].text = "Gyroscope\n(simulation)"
            self.labels["env"].text = "Environnement\nBME280 absent"
            self.labels["status"].text = "Etat\nBus I2C inactif"
            self.labels["status"].color = theme_manager.get_color("warning")
            return

        try:
            ax = self.read_word(ACCEL_XOUT_H) / ACCEL_SCALE
            ay = self.read_word(ACCEL_XOUT_H + 2) / ACCEL_SCALE
            az = self.read_word(ACCEL_XOUT_H + 4) / ACCEL_SCALE
            gx = self.read_word(GYRO_XOUT_H) / GYRO_SCALE
            gy = self.read_word(GYRO_XOUT_H + 2) / GYRO_SCALE
            gz = self.read_word(GYRO_XOUT_H + 4) / GYRO_SCALE
        except Exception as error:
            self.labels["status"].text = "Etat\nErreur I2C"
            print("[capteurs] lecture : {}".format(error))
            return

        self.labels["accel"].text = "Accelerometre (g)\nX {:+.2f}  Y {:+.2f}  Z {:+.2f}".format(ax, ay, az)
        self.labels["gyro"].text = "Gyroscope (dps)\nX {:+.1f}  Y {:+.1f}  Z {:+.1f}".format(gx, gy, gz)
        self.labels["env"].text = "Environnement\nBME280 a integrer"
        self.labels["status"].text = "Etat\nI2C actif"
        self.labels["status"].color = theme_manager.get_color("success")

    def on_cleanup(self):
        if getattr(self, "_clock", None) is not None:
            self._clock.cancel()
        if self.bus is not None:
            try:
                self.bus.close()
            except Exception:
                pass


NovaApp = SensorsApp
