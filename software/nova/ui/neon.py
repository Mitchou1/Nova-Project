#!/usr/bin/env python3
"""Effets néon pour NOVA (halo lumineux simulé).

Kivy n'a pas de flou gaussien simple à appliquer sur du texte. On simule donc
le halo en superposant plusieurs copies du texte, décalées dans huit
directions et très transparentes : de loin, cela donne l'impression d'une
lueur diffuse. Plus il y a de couches, plus c'est fidèle — et plus c'est
coûteux. L'effet est donc désactivable pour le Raspberry Pi.

Composants :
  - GlowLabel : un Label entouré de son halo.
  - NeonFrame : un cadre rectangulaire lumineux (plusieurs contours superposés).
"""

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from nova.utils.config_loader import get_config
from nova.utils.platform_utils import is_raspberry_pi

# Décalages du halo (huit directions)
_OFFSETS = [(1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (-1, -1), (1, -1), (-1, 1)]


def glow_enabled():
    value = get_config().get("ui", {}).get("glow", "auto")
    if isinstance(value, str) and value.lower() == "auto":
        return not is_raspberry_pi()
    return bool(value)


class GlowLabel(FloatLayout):
    """Texte net entouré d'un halo coloré simulé."""

    def __init__(self, text="", font_name=None, font_size=dp(20),
                 color=(1, 1, 1, 1), glow_color=None, glow_layers=3,
                 bold=False, halign="left", valign="middle", **kwargs):
        super().__init__(**kwargs)
        self._text = text
        self._font_name = font_name
        self._font_size = font_size
        self._color = color
        self._glow_color = glow_color or color
        self._layers = glow_layers if glow_enabled() else 0
        self._bold = bold
        self._halign = halign
        self._valign = valign
        self._halo = []
        self._build()

    def _mk(self, color):
        lbl = Label(text=self._text, font_size=self._font_size, bold=self._bold,
                    color=color, halign=self._halign, valign=self._valign,
                    size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        if self._font_name:
            lbl.font_name = self._font_name
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        return lbl

    def _build(self):
        # Couches de halo resserrées : lueur fine et nette plutôt que masse floue.
        # Étalement réduit (2.5 px max) et alpha un peu plus francs sur la couche
        # proche, pour un liseré lumineux net collé au texte.
        spreads = [(2.5, 0.10), (1.4, 0.16), (0.7, 0.22)][:self._layers]
        r, g, b = self._glow_color[:3]
        for spread, alpha in spreads:
            for dx, dy in _OFFSETS:
                lbl = self._mk((r, g, b, alpha))
                lbl.pos_hint = {"center_x": 0.5 + dx * spread / 300.0,
                                "center_y": 0.5 + dy * spread / 200.0}
                lbl.size_hint = (1, 1)
                self._halo.append(lbl)
                self.add_widget(lbl)
        # Texte net au-dessus
        self.main = self._mk(self._color)
        self.add_widget(self.main)

    def set_text(self, text):
        self._text = text
        for lbl in self._halo:
            lbl.text = text
        self.main.text = text

    def set_colors(self, color, glow_color=None):
        self._color = color
        self._glow_color = glow_color or color
        self.main.color = color
        r, g, b = self._glow_color[:3]
        spreads = [0.10, 0.16, 0.22]
        # réappliquer l'alpha par couche (les halos gardent leur ordre)
        idx = 0
        for si, (_spread, alpha) in enumerate(zip([6, 4, 2], spreads)):
            for _off in _OFFSETS:
                if idx < len(self._halo):
                    self._halo[idx].color = (r, g, b, alpha)
                    idx += 1


class NeonFrame(FloatLayout):
    """Cadre rectangulaire lumineux (contours superposés de plus en plus larges).

    Sert au bloc « mission » du mode cyberpunk. Ajoutez le contenu comme enfant.
    """

    def __init__(self, color=(1, 0, 0.24, 1), radius=dp(4), core_width=1.6,
                 fill_key=None, **kwargs):
        super().__init__(**kwargs)
        self._color = color
        self._radius = radius
        self._core_width = core_width
        self._layers = 3 if glow_enabled() else 0

        with self.canvas.before:
            if fill_key is not None:
                from nova.ui.theme import theme
                self._fill_col = Color(*theme.get_rgba(fill_key))
                self._fill = RoundedRectangle(radius=[radius])
            else:
                self._fill = None
            # halos (du plus large/faible au plus serré) puis trait net
            self._halo_colors = []
            self._halo_lines = []
            for width, alpha in [(7, 0.06), (4.5, 0.10), (2.5, 0.18)][:self._layers]:
                c = Color(color[0], color[1], color[2], alpha)
                ln = Line(width=width)
                self._halo_colors.append((c, alpha))
                self._halo_lines.append(ln)
            self._core_col = Color(*color)
            self._core_line = Line(width=core_width)

        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *_):
        x, y, w, h = self.x, self.y, self.width, self.height
        if w <= 0 or h <= 0:
            return
        if self._fill is not None:
            self._fill.pos = (x, y)
            self._fill.size = (w, h)
            self._fill.radius = [self._radius]
        rr = (x, y, w, h, self._radius)
        for ln in self._halo_lines:
            ln.rounded_rectangle = rr
        self._core_line.rounded_rectangle = rr

    def set_color(self, color):
        self._color = color
        self._core_col.rgba = color
        for (c, alpha), _ln in zip(self._halo_colors, self._halo_lines):
            c.rgba = (color[0], color[1], color[2], alpha)
