#!/usr/bin/env python3
"""Écran de veille NOVA.

Après un temps sans toucher l'écran, l'appareil s'assombrit et affiche le
logo NOVA avec des effets visuels : respiration lumineuse, anneau qui
tourne, ligne de balayage et heure discrète.

Le moindre contact réveille l'appareil et rend la main à l'écran précédent.
"""

import math

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from nova import fonts
from nova.ui.theme import theme


class ScanRing(Widget):
    """Anneau lumineux qui tourne lentement autour du logo."""

    angle = NumericProperty(0)

    def __init__(self, rayon=dp(74), **kwargs):
        super().__init__(**kwargs)
        self.rayon = rayon
        with self.canvas:
            self._couleur_fond = Color(*theme.get_rgba("primary", 0.12))
            self._cercle = Line(width=dp(1.1))
            self._couleur_arc = Color(*theme.get_rgba("primary", 0.85))
            self._arc = Line(width=dp(2.2))
        self.bind(pos=self._redraw, size=self._redraw, angle=self._redraw)

    def _redraw(self, *_a):
        cx, cy = self.center
        r = self.rayon
        # Cercle complet, très discret
        self._cercle.circle = (cx, cy, r)
        # Arc lumineux qui tourne (un quart de cercle)
        self._arc.circle = (cx, cy, r, self.angle, self.angle + 90)

    def start(self):
        Animation.cancel_all(self, "angle")
        self.angle = 0
        anim = Animation(angle=360, duration=4.0, t="linear")
        anim.repeat = True
        anim.start(self)

    def stop(self):
        Animation.cancel_all(self, "angle")


class SleepOverlay(FloatLayout):
    """Voile de veille : fond noir, logo NOVA animé, heure discrète."""

    def __init__(self, on_wake=None, **kwargs):
        super().__init__(**kwargs)
        self.on_wake = on_wake
        self.opacity = 0
        self.disabled = True
        self._scan_pos = 0.0
        self._clock = None

        # Fond noir opaque
        with self.canvas.before:
            self._fond_color = Color(0, 0, 0, 0.97)
            self._fond = Rectangle()
        self.bind(pos=self._place_fond, size=self._place_fond)

        # Anneau tournant derrière le logo
        self.ring = ScanRing(size_hint=(None, None), size=(dp(160), dp(160)),
                             pos_hint={"center_x": 0.5, "center_y": 0.54})
        self.add_widget(self.ring)

        # Halo doux derrière le logo
        with self.canvas:
            self._halo_color = Color(*theme.get_rgba("primary", 0.10))
            self._halo = Ellipse()

        # Logo NOVA
        self.logo = Label(
            text="NOVA", font_name=fonts.FONT_DISPLAY_XL, bold=True,
            font_size=dp(44),
            color=theme.get_rgba("primary"),
            size_hint=(1, None), height=dp(56),
            pos_hint={"center_x": 0.5, "center_y": 0.54},
        )
        self.add_widget(self.logo)

        # Sous-titre en label-caps (charte NOVA)
        self.sous_titre = Label(
            text="V E I L L E", font_name=fonts.FONT_MONO, font_size=dp(9),
            color=theme.get_rgba("text_secondary"),
            size_hint=(1, None), height=dp(16),
            pos_hint={"center_x": 0.5, "center_y": 0.44},
        )
        self.add_widget(self.sous_titre)

        # Heure discrète en bas
        self.heure = Label(
            text="", font_name=fonts.FONT_MONO, font_size=dp(13),
            color=theme.get_rgba("text_secondary"),
            size_hint=(1, None), height=dp(20),
            pos_hint={"center_x": 0.5, "y": 0.10},
        )
        self.add_widget(self.heure)

        # Indication de réveil
        self.aide = Label(
            text="TOUCHEZ L'ÉCRAN", font_name=fonts.FONT_MONO, font_size=dp(8),
            color=theme.get_rgba("text_secondary", 0.5),
            size_hint=(1, None), height=dp(14),
            pos_hint={"center_x": 0.5, "y": 0.04},
        )
        self.add_widget(self.aide)

        # Ligne de balayage qui traverse l'écran
        with self.canvas.after:
            self._scan_color = Color(*theme.get_rgba("primary", 0))
            self._scan = Rectangle()

    # --- dessin ---------------------------------------------------------
    def _place_fond(self, *_a):
        self._fond.pos = self.pos
        self._fond.size = self.size
        cx, cy = self.center_x, self.y + self.height * 0.54
        r = dp(96)
        self._halo.pos = (cx - r, cy - r)
        self._halo.size = (r * 2, r * 2)
        self._place_scan()

    def _place_scan(self, *_a):
        y = self.y + self.height * self._scan_pos
        self._scan.pos = (self.x, y)
        self._scan.size = (self.width, dp(1.6))

    def _set_scan(self, valeur):
        self._scan_pos = valeur
        self._place_scan()

    scan_pos = property(lambda self: self._scan_pos, _set_scan)

    # --- cycle de vie ---------------------------------------------------
    def show(self):
        """Entre en veille : apparition en fondu et démarrage des effets."""
        self.disabled = False
        Animation.cancel_all(self, "opacity")
        Animation(opacity=1, duration=0.6, t="out_quad").start(self)

        # Le logo « respire »
        Animation.cancel_all(self.logo, "opacity")
        respire = (Animation(opacity=0.35, duration=2.2, t="in_out_sine")
                   + Animation(opacity=1.0, duration=2.2, t="in_out_sine"))
        respire.repeat = True
        respire.start(self.logo)

        self.ring.start()
        self._start_scan()
        self._maj_heure()
        self._clock = Clock.schedule_interval(self._maj_heure, 10)

    def hide(self):
        """Sort de veille : disparition et arrêt de toutes les animations."""
        self.disabled = True
        Animation.cancel_all(self, "opacity")
        Animation(opacity=0, duration=0.25, t="out_quad").start(self)

        Animation.cancel_all(self.logo, "opacity")
        self.logo.opacity = 1
        self.ring.stop()
        Animation.cancel_all(self, "scan_pos")
        self._scan_color.rgba = theme.get_rgba("primary", 0)
        if self._clock is not None:
            self._clock.cancel()
            self._clock = None

    def _start_scan(self):
        """Ligne lumineuse qui descend en boucle sur tout l'écran."""
        self._scan_color.rgba = theme.get_rgba("primary", 0.35)
        Animation.cancel_all(self, "scan_pos")
        self.scan_pos = 1.0
        anim = Animation(scan_pos=0.0, duration=3.2, t="linear")
        anim.repeat = True
        anim.start(self)

    def _maj_heure(self, *_a):
        from datetime import datetime
        maintenant = datetime.now()
        self.heure.text = maintenant.strftime("%H:%M")

    # --- réveil ---------------------------------------------------------
    def on_touch_down(self, touch):
        """N'importe quel contact réveille l'appareil.

        Quand le voile est invisible (hors veille), il doit laisser passer
        TOUS les contacts vers l'interface, sinon l'écran devient inutilisable.
        """
        if self.disabled or self.opacity <= 0.05:
            return False          # invisible : on ne touche a rien
        if self.collide_point(*touch.pos):
            if self.on_wake:
                self.on_wake()
            return True           # en veille : le contact sert au reveil
        return False
