#!/usr/bin/env python3
"""Widgets premium NOVA : glassmorphism, anneaux, particules, waveform.

Tous les effets animés sont désactivables : sur Raspberry Pi Zero 2 W, les
particules et le visualiseur consomment plus de CPU que tout le reste de
l'interface réunie. Voir `effects_enabled()`.
"""

import math
import random

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from nova.ui.theme import theme
from nova.utils.config_loader import get_config
from nova.utils.platform_utils import is_raspberry_pi


def effects_enabled(name, default="auto"):
    """Lit config/system.json -> "ui": {"particles": true|false|"auto"}.

    "auto" = actif sur PC, coupé sur Raspberry Pi.
    """
    value = get_config().get("ui", {}).get(name, default)
    if isinstance(value, str) and value.lower() == "auto":
        return not is_raspberry_pi()
    return bool(value)


# ---------------------------------------------------------------------------
# Carte en verre dépoli
# ---------------------------------------------------------------------------
class GlassCard(FloatLayout):
    """Carte glassmorphism : ombre, fond translucide, bordure, halo.

    Suit la charte NOVA (Stitch) :
      - `chamfer` > 0 coupe le coin haut-droit à 45° (tuiles d'application) ;
      - en mode Undercover la bordure devient pointillée et le fond disparaît ;
      - `scanline` anime une ligne turquoise à l'appui.
    """

    corner_radius = NumericProperty(dp(2))   # Charte NOVA : forme "Sharp"
    border_width = NumericProperty(1.2)
    glow_intensity = NumericProperty(0.35)
    animate_on_touch = BooleanProperty(True)
    # Retrait animé lors de l'appui (remplace un "scale" que FloatLayout n'a pas)
    press_inset = NumericProperty(0)
    # Coin haut-droit coupé à 45° (0 = désactivé). Charte : 8px sur les tuiles.
    chamfer = NumericProperty(0)
    # Ligne de balayage à l'appui (0 = cachée, 1 = en haut de la carte)
    scanline_pos = NumericProperty(0)
    scanline_enabled = BooleanProperty(False)

    def __init__(self, **kwargs):
        super(GlassCard, self).__init__(**kwargs)
        self._build_canvas()
        self.bind(pos=self._refresh, size=self._refresh,
                  press_inset=self._refresh, corner_radius=self._refresh,
                  chamfer=self._refresh, scanline_pos=self._refresh)
        theme.bind(on_theme_change=self._on_theme_change)

    def _build_canvas(self):
        with self.canvas.before:
            self.shadow_color = Color(0, 0, 0, 0.35)
            self.shadow = RoundedRectangle(radius=[self.corner_radius])

            self.bg_color = Color(*theme.get_rgba("glass"))
            self.bg = RoundedRectangle(radius=[self.corner_radius])

            self.glow_color = Color(*theme.get_rgba("primary", self.glow_intensity * 0.3))
            self.glow = Ellipse()

            self.border_color = Color(*theme.get_rgba("glass_border"))
            self.border = Line(width=self.border_width)

            # Ligne de balayage (charte : animation "scanline" à l'appui)
            self.scan_color = Color(*theme.get_rgba("primary", 0))
            self.scan = Line(width=dp(1.4))

    def _dashes(self):
        """Bordure pointillée en Undercover (charte : flat outlines)."""
        if getattr(theme, "name", "") == "undercover":
            return 4, 3
        return 1, 0

    def _refresh(self, *_args):
        inset = self.press_inset
        x = self.x + inset
        y = self.y + inset
        width = max(1.0, self.width - inset * 2)
        height = max(1.0, self.height - inset * 2)
        radius = [self.corner_radius]

        self.shadow.pos = (x + dp(3), y - dp(3))
        self.shadow.size = (width, height)
        self.shadow.radius = radius

        self.bg.pos = (x, y)
        self.bg.size = (width, height)
        self.bg.radius = radius

        self.glow.pos = (x + width * 0.2, y + height - dp(3))
        self.glow.size = (width * 0.6, dp(6))

        dash_len, dash_off = self._dashes()
        self.border.dash_length = dash_len
        self.border.dash_offset = dash_off

        if self.chamfer > 0:
            # Contour à 5 points : coin haut-droit coupé à 45°
            c = min(self.chamfer, width * 0.5, height * 0.5)
            self.border.points = [
                x, y,
                x + width, y,
                x + width, y + height - c,
                x + width - c, y + height,
                x, y + height,
                x, y,
            ]
        else:
            self.border.points = []
            self.border.rounded_rectangle = (x, y, width, height, self.corner_radius)

        # Position de la ligne de balayage
        if self.scanline_pos > 0:
            sy = y + height * self.scanline_pos
            self.scan.points = [x + dp(2), sy, x + width - dp(2), sy]
        else:
            self.scan.points = []

    def _on_theme_change(self, *_args):
        self.bg_color.rgba = theme.get_rgba("glass")
        self.border_color.rgba = theme.get_rgba("glass_border")
        self.glow_color.rgba = theme.get_rgba("primary", self.glow_intensity * 0.3)
        self._refresh()

    def _start_scanline(self):
        """Balaye une ligne turquoise de bas en haut (charte : état pressé)."""
        self.scan_color.rgba = theme.get_rgba("primary", 0.5)
        Animation.cancel_all(self, "scanline_pos")
        self.scanline_pos = 0.01
        anim = Animation(scanline_pos=1.0, duration=0.45, t="linear")
        anim.bind(on_complete=lambda *_: self._end_scanline())
        anim.start(self)

    def _end_scanline(self):
        self.scanline_pos = 0
        self.scan_color.rgba = theme.get_rgba("primary", 0)

    # --- interaction -----------------------------------------------------
    def on_touch_down(self, touch):
        if self.animate_on_touch and self.collide_point(*touch.pos):
            Animation.cancel_all(self, "press_inset")
            Animation(press_inset=dp(3), duration=0.08, t="out_quad").start(self)
            if self.scanline_enabled:
                self._start_scanline()
        return super(GlassCard, self).on_touch_down(touch)

    def on_touch_up(self, touch):
        # Toujours relacher l'etat enfonce, meme si le touch_up arrive
        # hors de la carte (ex. pendant une transition d'ecran) : sinon la
        # carte peut rester "enfoncee" et sembler ne plus repondre.
        if self.press_inset:
            Animation.cancel_all(self, "press_inset")
            Animation(press_inset=0, duration=0.25, t="out_elastic").start(self)
        return super(GlassCard, self).on_touch_up(touch)

    def on_leave(self, *args):
        """Reinitialise l'etat visuel quand l'ecran parent est quitte."""
        Animation.cancel_all(self, "press_inset")
        self.press_inset = 0


# ---------------------------------------------------------------------------
# Anneau de progression
# ---------------------------------------------------------------------------
class CircularProgress(Widget):
    """Anneau de progression animé, avec valeur affichée au centre."""

    value = NumericProperty(0)
    max_value = NumericProperty(100)
    stroke_width = NumericProperty(dp(5))
    ring_color = ListProperty([0, 0.83, 0.67, 1])
    track_color = ListProperty([1, 1, 1, 0.10])
    animated = BooleanProperty(True)
    suffix = StringProperty("%")
    show_label = BooleanProperty(True)

    def __init__(self, **kwargs):
        super(CircularProgress, self).__init__(**kwargs)
        self.ring_color = list(theme.get_rgba("primary"))

        self.label = Label(text="", font_size=dp(13), bold=True,
                           color=theme.get_rgba("text_primary"))
        self.add_widget(self.label)

        with self.canvas:
            self.track_instruction_color = Color(*self.track_color)
            # Line(circle=...) dessine un ARC, contrairement a Ellipse qui
            # remplit un disque : c'est ce qui donne l'anneau.
            self.track = Line(width=self.stroke_width, cap="round")

            self.ring_instruction_color = Color(*self.ring_color)
            self.ring = Line(width=self.stroke_width, cap="round")

        self.bind(pos=self._refresh, size=self._refresh, value=self._refresh,
                  ring_color=self._refresh, track_color=self._refresh)
        self._refresh()

    def _refresh(self, *_args):
        radius = max(dp(6), min(self.width, self.height) / 2.0 - self.stroke_width)
        center_x, center_y = self.center

        self.track.circle = (center_x, center_y, radius, 0, 360)
        self.track.width = self.stroke_width
        self.track_instruction_color.rgba = self.track_color

        ratio = 0.0
        if self.max_value:
            ratio = max(0.0, min(1.0, self.value / float(self.max_value)))
        self.ring.circle = (center_x, center_y, radius, 0, 360 * ratio)
        self.ring.width = self.stroke_width
        self.ring_instruction_color.rgba = self.ring_color

        self.label.center = self.center
        self.label.opacity = 1 if self.show_label else 0
        self.label.text = "{:.0f}{}".format(self.value, self.suffix)

    def set_value(self, value, animate=None):
        """Change la valeur. L'animation porte sur la propriete `value`,
        dont chaque variation redessine l'arc via `_refresh`."""
        target = max(0, min(float(value), self.max_value))
        use_animation = self.animated if animate is None else animate

        Animation.cancel_all(self, "value")
        if use_animation:
            Animation(value=target, duration=0.5, t="out_cubic").start(self)
        else:
            self.value = target


# ---------------------------------------------------------------------------
# Bouton néon
# ---------------------------------------------------------------------------
class NeonButton(ButtonBehavior, GlassCard):
    """Tuile / bouton : carte en verre + réaction néon à l'appui.

    L'icône est rendue avec la police Material (police d'icônes) et non la
    police de texte : c'est ce qui évite les carrés « tofu » quand on passe
    un symbole ou un emoji. `icon` accepte soit un nom Material connu
    (ex. "radio", "add"), soit un ancien symbole/emoji qui sera traduit.
    """

    text = StringProperty("")
    icon = StringProperty("")
    accent = StringProperty("primary")
    font_size = NumericProperty(dp(15))
    icon_size = NumericProperty(dp(22))

    # Traduction des anciens symboles/emojis vers un nom d'icône Material
    _SYMBOL_MAP = {
        "◀": "chevron_left", "▶": "chevron_right",
        "‹": "chevron_left", "›": "chevron_right",
        "◁": "chevron_left", "▷": "chevron_right",
        "+": "add", "＋": "add",
        "×": "close", "✕": "close", "✖": "close", "X": "close",
        "●": "circle", "⏹": "stop", "■": "stop",
        "🔍": "search", "🔄": "restart_alt",
        "⚠️": "warning", "⚠": "warning",
        "🗑": "delete", "🗑️": "delete",
        "▲": "chevron_left", "▼": "chevron_right",
    }

    def __init__(self, **kwargs):
        # Charte NOVA : forme "Sharp" par defaut (angles nets)
        kwargs.setdefault("corner_radius", dp(2))
        super(NeonButton, self).__init__(**kwargs)

        from nova import fonts
        self._fonts = fonts

        # Conteneur vertical : icône (Material) au-dessus, texte en dessous
        self._box = BoxLayout(orientation="vertical", size_hint=(1, 1),
                              pos_hint={"x": 0, "y": 0}, padding=dp(4), spacing=dp(2))

        self.icon_label = Label(
            font_name=fonts.FONT_ICON, font_size=self.icon_size,
            halign="center", valign="middle",
            color=theme.get_rgba("text_primary"), size_hint=(1, 0.55))
        self.icon_label.bind(size=lambda w, s: setattr(w, "text_size", s))

        self.label = Label(
            font_name=fonts.FONT_MONO, font_size=self.font_size,
            halign="center", valign="middle",
            color=theme.get_rgba("text_primary"), size_hint=(1, 0.45))
        self.label.bind(size=lambda w, s: setattr(w, "text_size", s))

        self._box.add_widget(self.icon_label)
        self._box.add_widget(self.label)
        self.add_widget(self._box)

        self.bind(text=self._refresh_label, icon=self._refresh_label,
                  font_size=self._refresh_label, icon_size=self._refresh_label)
        self._refresh_label()

    def _resolve_icon_char(self):
        """Renvoie le glyphe Material à afficher pour self.icon (ou '')."""
        if not self.icon:
            return ""
        fonts = self._fonts
        # 1) déjà un nom Material connu
        if fonts.has_icon(self.icon):
            return fonts.icon(self.icon)
        # 2) ancien symbole/emoji -> nom Material
        name = self._SYMBOL_MAP.get(self.icon)
        if name and fonts.has_icon(name):
            return fonts.icon(name)
        # 3) inconnu : ne rien afficher plutôt qu'un carré
        return ""

    def _refresh_label(self, *_args):
        glyph = self._resolve_icon_char()
        self.icon_label.font_size = self.icon_size
        self.label.font_size = self.font_size

        has_icon = bool(glyph)
        has_text = bool(self.text)

        self.icon_label.text = glyph
        # Charte : les libelles de boutons sont des « commandes »
        self.label.text = self.text.upper()

        # Ajuster la répartition icône/texte selon ce qui est présent.
        # Important : on RETIRE le label inutilisé de la boîte au lieu de lui
        # donner une hauteur nulle — sinon Kivy replace mal l'icône (elle
        # sortait du bouton et se dessinait au-dessus).
        def _ensure(widget, present, hint):
            inside = widget.parent is self._box
            if present and not inside:
                self._box.add_widget(widget)
            elif not present and inside:
                self._box.remove_widget(widget)
            if present:
                widget.size_hint_y = hint

        if has_icon and has_text:
            _ensure(self.icon_label, True, 0.55)
            _ensure(self.label, True, 0.45)
        elif has_icon:
            _ensure(self.label, False, 0)
            _ensure(self.icon_label, True, 1)
        else:
            _ensure(self.icon_label, False, 0)
            _ensure(self.label, True, 1)

    def _resize_label(self, widget, size):
        widget.text_size = (size[0] * 0.9, size[1])

    def on_press(self):
        self.border_color.rgba = theme.get_rgba(self.accent, 0.85)
        self.glow_color.rgba = theme.get_rgba(self.accent, 0.45)

    def on_release(self):
        self.border_color.rgba = theme.get_rgba("glass_border")
        self.glow_color.rgba = theme.get_rgba("primary", self.glow_intensity * 0.3)


# ---------------------------------------------------------------------------
# Fond animé
# ---------------------------------------------------------------------------
class ParticleBackground(Widget):
    """Particules flottantes. Inactif si `ui.particles` est désactivé."""

    particle_count = NumericProperty(18)
    speed = NumericProperty(1.0)
    fps = NumericProperty(30)

    def __init__(self, **kwargs):
        super(ParticleBackground, self).__init__(**kwargs)
        self.particles = []
        self._ellipses = []
        self._clock = None

        if not effects_enabled("particles"):
            return

        self._spawn()
        self._clock = Clock.schedule_interval(self._step, 1.0 / max(1, self.fps))

    def _spawn(self):
        palette = ("primary", "secondary", "accent")
        with self.canvas:
            for _ in range(int(self.particle_count)):
                particle = {
                    "x": random.uniform(0, Window.width),
                    "y": random.uniform(0, Window.height),
                    "size": random.uniform(dp(2), dp(5)),
                    "dx": random.uniform(-0.4, 0.4),
                    "dy": random.uniform(-0.8, -0.25),
                }
                self.particles.append(particle)
                Color(*theme.get_rgba(random.choice(palette),
                                      random.uniform(0.10, 0.35)))
                self._ellipses.append(Ellipse(
                    pos=(particle["x"], particle["y"]),
                    size=(particle["size"], particle["size"]),
                ))

    def _step(self, _dt):
        width, height = Window.width, Window.height
        for particle, ellipse in zip(self.particles, self._ellipses):
            particle["x"] += particle["dx"] * self.speed
            particle["y"] += particle["dy"] * self.speed

            if particle["y"] < -dp(10):
                particle["y"] = height + dp(10)
                particle["x"] = random.uniform(0, width)
            if particle["x"] < -dp(10):
                particle["x"] = width + dp(10)
            elif particle["x"] > width + dp(10):
                particle["x"] = -dp(10)

            ellipse.pos = (particle["x"], particle["y"])

    def stop(self):
        if self._clock is not None:
            self._clock.cancel()
            self._clock = None


# ---------------------------------------------------------------------------
# Visualiseur d'onde
# ---------------------------------------------------------------------------
class WaveformVisualizer(Widget):
    """Barres animées. `active=False` met l'onde au repos (CPU quasi nul)."""

    bar_count = NumericProperty(28)
    amplitude = NumericProperty(0.45)
    active = BooleanProperty(True)
    fps = NumericProperty(24)

    def __init__(self, **kwargs):
        super(WaveformVisualizer, self).__init__(**kwargs)
        self._bars = []
        self._colors = []
        self._clock = None
        self._phase = 0.0

        self._build_bars()
        self.bind(pos=self._layout_bars, size=self._layout_bars)

        if effects_enabled("waveform"):
            self._clock = Clock.schedule_interval(self._step, 1.0 / max(1, self.fps))

    def _build_bars(self):
        start = theme.get_rgba("gradient_start")
        end = theme.get_rgba("gradient_end")
        count = max(1, int(self.bar_count))

        with self.canvas:
            for index in range(count):
                ratio = index / float(count - 1) if count > 1 else 0.0
                self._colors.append(Color(*self._mix(start, end, ratio)))
                self._bars.append(Rectangle(size=(dp(2), dp(2))))

    @staticmethod
    def _mix(color_a, color_b, ratio):
        return tuple(a + (b - a) * ratio for a, b in zip(color_a, color_b))

    def _layout_bars(self, *_args):
        count = len(self._bars)
        if not count or self.width <= 0:
            return
        slot = self.width / float(count)
        for index, bar in enumerate(self._bars):
            height = max(dp(2), bar.size[1])
            bar.size = (slot * 0.55, height)
            bar.pos = (self.x + index * slot, self.center_y - height / 2.0)

    def _step(self, dt):
        if self.width <= 0:
            return
        self._phase += dt * 3.0
        count = len(self._bars)
        slot = self.width / float(count)
        amplitude = self.amplitude if self.active else 0.04

        for index, bar in enumerate(self._bars):
            wave = abs(math.sin(self._phase + index * 0.35))
            height = wave * self.height * amplitude + random.uniform(-1.5, 1.5)
            height = max(dp(2), min(height, self.height))
            bar.size = (slot * 0.55, height)
            bar.pos = (self.x + index * slot, self.center_y - height / 2.0)

    def stop(self):
        if self._clock is not None:
            self._clock.cancel()
            self._clock = None


# ---------------------------------------------------------------------------
# Compatibilité : noms utilisés par les applications déjà écrites
# ---------------------------------------------------------------------------
class Card(GlassCard):
    """Ancien nom conservé pour ne rien casser dans les apps."""


class IconButton(NeonButton):
    """Ancien nom conservé pour ne rien casser dans les apps."""

    def __init__(self, icon="", text="", **kwargs):
        super(IconButton, self).__init__(icon=icon, text=text, **kwargs)


class TitleLabel(Label):
    """Titre de section."""

    def __init__(self, text="", **kwargs):
        kwargs.setdefault("font_size", dp(19))
        kwargs.setdefault("bold", True)
        kwargs.setdefault("color", theme.get_rgba("text_primary"))
        super(TitleLabel, self).__init__(text=text, **kwargs)
