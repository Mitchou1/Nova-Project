#!/usr/bin/env python3
"""Cartes et cadres dont le style suit le mode actif.

Trois personnalités visuelles :
  - classic     : coins arrondis, bordure fine translucide (glassmorphism)
  - cyberpunk   : coins chanfreinés à 45°, bordure néon épaisse
  - undercover  : coins droits, bordure pointillée fine (terminal)

Le style se recalcule automatiquement à chaque changement de thème.
"""

import math

from kivy.graphics import Color, Line, Mesh, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout

from nova.ui.theme import theme


def chamfer_points(x, y, w, h, cut):
    """Sommets d'un rectangle à coins coupés (chanfrein), sens horaire."""
    return [
        x + cut, y,
        x + w - cut, y,
        x + w, y + cut,
        x + w, y + h - cut,
        x + w - cut, y + h,
        x + cut, y + h,
        x, y + h - cut,
        x, y + cut,
    ]


def _mesh_from_polygon(flat_pts):
    """Convertit une liste plate [x0,y0,x1,y1,...] en (vertices, indices) pour un Mesh plein (triangle fan)."""
    n = len(flat_pts) // 2
    cx = sum(flat_pts[0::2]) / n
    cy = sum(flat_pts[1::2]) / n
    vertices = [cx, cy, 0, 0]
    for i in range(n):
        vertices += [flat_pts[2 * i], flat_pts[2 * i + 1], 0, 0]
    indices = []
    for i in range(1, n + 1):
        nxt = i + 1 if i < n else 1
        indices += [0, i, nxt]
    return vertices, indices


class ModeCard(FloatLayout):
    """Conteneur dont le fond et la bordure suivent le mode actif.

    Ajoutez votre contenu comme enfant (avec pos_hint pour rester dans la carte).
    """

    def __init__(self, radius=dp(14), border_width=None, fill_key="surface",
                 border_key="glass_border", accent_border=False, **kwargs):
        super().__init__(**kwargs)
        self.radius = radius
        self.border_width = border_width
        self.fill_key = fill_key
        self.border_key = border_key
        self.accent_border = accent_border
        self._border_override = None

        with self.canvas.before:
            self._fill_color = Color(*theme.get_rgba(fill_key))
            self._mesh = Mesh(mode="triangle_fan")
            self._round = RoundedRectangle()
            self._border_color = Color(*self._border_rgba())
            self._line = Line()

        self.bind(pos=self._redraw, size=self._redraw)
        theme.bind(on_theme_change=lambda *_a: self._redraw())

    def _border_rgba(self):
        if self._border_override is not None:
            return self._border_override
        key = "primary" if self.accent_border else self.border_key
        return theme.get_rgba(key)

    def set_border_override(self, rgba):
        """Force une couleur de bordure (None = revenir au style du mode)."""
        self._border_override = rgba
        self._redraw()

    def _mode_border_width(self):
        if self.border_width is not None:
            return self.border_width
        name = theme.name
        if name == "cyberpunk":
            return 2.0
        if name == "undercover":
            return 1.0
        return 1.1

    def _redraw(self, *_):
        name = theme.name
        x, y, w, h = self.x, self.y, self.width, self.height
        if w <= 0 or h <= 0:
            return

        self._fill_color.rgba = theme.get_rgba(self.fill_key)
        self._border_color.rgba = self._border_rgba()
        bw = self._mode_border_width()

        # Réinitialiser les trois tracés (on n'en montre qu'un selon le mode)
        self._mesh.vertices = []
        self._mesh.indices = []
        self._round.pos = (-9999, -9999)
        self._round.size = (0, 0)
        self._line.points = []
        self._line.rounded_rectangle = (0, 0, 0, 0, 0)

        if name == "cyberpunk":
            cut = dp(12)
            poly = chamfer_points(x, y, w, h, cut)
            verts, idx = _mesh_from_polygon(poly)
            self._mesh.vertices = verts
            self._mesh.indices = idx
            self._line.width = bw
            self._line.points = poly + poly[0:2]   # referme le contour
        elif name == "undercover":
            self._round.pos = (x, y)
            self._round.size = (w, h)
            self._round.radius = [dp(2)]
            self._line.width = bw
            self._line.dash_length = dp(4)
            self._line.dash_offset = dp(3)
            self._line.rounded_rectangle = (x, y, w, h, dp(2))
        else:  # classic
            self._round.pos = (x, y)
            self._round.size = (w, h)
            self._round.radius = [self.radius]
            self._line.width = bw
            self._line.dash_length = 100000     # trait plein
            self._line.dash_offset = 0
            self._line.rounded_rectangle = (x, y, w, h, self.radius)

    def set_accent(self, on=True):
        self.accent_border = on
        self._redraw()
