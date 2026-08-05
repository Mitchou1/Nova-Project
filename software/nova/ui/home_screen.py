#!/usr/bin/env python3
"""Écran d'accueil NOVA — style Stitch, trois modes commutables.

Le look reprend les maquettes : horloge Sora géante, date en mono, carte
"prochain événement", grille de tuiles avec icônes Material, et barre de
navigation basse dont le bouton palette fait tourner les modes
Classic -> Cyberpunk -> Undercover.

La grille d'applications reste alimentée par AppLauncher : ajouter un dossier
dans software/apps/ suffit toujours à voir apparaître une tuile.
"""

import math
from datetime import datetime

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from nova import fonts
from nova.ui.theme import theme
from nova.ui.mode_card import ModeCard, chamfer_points
from nova.ui.neon import GlowLabel, NeonFrame, glow_enabled
from nova.ui.widgets import GlassCard

# Icône Material par app (repli sur "widgets" si inconnue)
ICON_BY_APP = {
    "assistant": "smart_toy",
    "maps": "explore",
    "calendar": "event_note",
    "sensors": "settings_input_component",
    "radio": "radio",
    "settings": "settings",
    "camera": "photo_camera",     # manquait : la tuile affichait du tofu
    "files": "folder",
}

# Ordre de bascule des modes (bouton palette)
MODE_CYCLE = ["classic", "cyberpunk", "undercover"]

MONTHS_FR = ("JANVIER", "FÉVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET",
             "AOÛT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DÉCEMBRE")
DAYS_FR = ("LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE")


def mode_is_sharp(name):
    """Cyberpunk et Undercover utilisent des angles vifs plutôt qu'arrondis."""
    return name in ("cyberpunk", "undercover")


def animations_enabled():
    """Animations actives ? 'auto' = oui sur PC, non sur Raspberry Pi.

    Coupées d'office en mode économie d'énergie (batterie basse, Phase 10).
    """
    from nova.power_manager import is_low_power_active
    if is_low_power_active():
        return False
    from nova.utils.config_loader import get_config
    from nova.utils.platform_utils import is_raspberry_pi
    value = get_config().get("ui", {}).get("animations", "auto")
    if isinstance(value, str) and value.lower() == "auto":
        return not is_raspberry_pi()
    return bool(value)


class MaterialIcon(Label):
    """Label affichant une icône Material par son nom, centrée."""

    def __init__(self, name, size=dp(24), color_key="primary", **kwargs):
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("valign", "middle")
        super().__init__(**kwargs)
        self.font_name = fonts.FONT_ICON
        self.font_size = size
        self.text = fonts.icon(name)
        self._color_key = color_key
        self.color = theme.get_rgba(color_key)
        # text_size = taille du widget => centrage correct, glyphe non coupé
        self.bind(size=lambda w, s: setattr(w, "text_size", s))
        theme.bind(on_theme_change=lambda *_a: setattr(self, "color", theme.get_rgba(self._color_key)))

    def set_icon(self, name):
        self.text = fonts.icon(name)


class AppTile(ButtonBehavior, FloatLayout):
    """Tuile d'application : icône Material + libellé, cadre selon le mode."""

    def __init__(self, app_id, name, icon_name, on_launch=None, **kwargs):
        super().__init__(**kwargs)
        self.app_id = app_id
        self.on_launch = on_launch
        self._pressed = 0

        from kivy.graphics import Mesh
        with self.canvas.before:
            self._fill = Color(*theme.get_rgba("surface_light"))
            self._mesh = Mesh(mode="triangle_fan")   # utilisé en cyberpunk
            self._rect = RoundedRectangle(radius=[dp(12)])  # utilisé sinon
            self._border = Color(*theme.get_rgba("glass_border"))
            self._line = Line(width=1.1)
        self.bind(pos=self._redraw, size=self._redraw)

        # pos_hint indispensable : dans un FloatLayout, sans lui l'enfant
        # reste collé à (0,0) de la fenêtre au lieu de suivre la tuile.
        box = BoxLayout(orientation="vertical", spacing=dp(6),
                        padding=dp(8), size_hint=(1, 1),
                        pos_hint={"x": 0, "y": 0})
        self.icon = MaterialIcon(icon_name, size=dp(44), color_key="primary",
                                 size_hint=(1, 0.66))
        self.caption = Label(text=name, font_name=fonts.FONT_MONO,
                             font_size=dp(12), size_hint=(1, 0.34),
                             halign="center", valign="middle",
                             color=theme.get_rgba("text_secondary"))
        self.caption.bind(size=lambda w, s: setattr(w, "text_size", s))
        box.add_widget(self.icon)
        box.add_widget(self.caption)
        self.add_widget(box)

        theme.bind(on_theme_change=self._on_theme)

        # Ligne de balayage (scanline) : dessinee par-dessus la tuile.
        # Elle descend du haut vers le bas, facon scanner futuriste.
        from kivy.graphics import Rectangle as _Rect
        with self.canvas.after:
            self._scan_color = Color(0, 0, 0, 0)
            self._scan_line = _Rect()
        self._scan_pos = 0.0          # 1.0 = en haut, 0.0 = en bas
        self._scan_anim = None
        self.bind(pos=self._place_scan, size=self._place_scan)

    # ------------------------------------------------------------------
    # Effet scanner : une ligne lumineuse traverse l'icone de haut en bas
    # ------------------------------------------------------------------
    def _place_scan(self, *_a):
        """Positionne la ligne selon l'avancement du balayage."""
        if not hasattr(self, "_scan_line"):
            return
        y = self.y + self.height * self._scan_pos
        self._scan_line.pos = (self.x + dp(4), y)
        self._scan_line.size = (max(0, self.width - dp(8)), dp(2))

    def _set_scan_pos(self, valeur):
        self._scan_pos = valeur
        self._place_scan()

    scan_pos = property(lambda self: self._scan_pos, _set_scan_pos)

    def scan(self, duree=1.4):
        """Fait descendre une ligne lumineuse du haut vers le bas."""
        from kivy.animation import Animation

        if self._scan_anim is not None:
            self._scan_anim.cancel(self)

        couleur = theme.get_rgba("primary")
        self._scan_color.rgba = (couleur[0], couleur[1], couleur[2], 0.9)
        self.scan_pos = 1.0

        # Descente de haut en bas, puis extinction
        anim = Animation(scan_pos=0.0, duration=duree, t="in_out_sine")
        anim.bind(on_complete=lambda *_a: setattr(self._scan_color, "rgba",
                                                  (0, 0, 0, 0)))
        self._scan_anim = anim
        anim.start(self)

    def stop_scan(self):
        """Coupe le balayage et efface la ligne."""
        if self._scan_anim is not None:
            self._scan_anim.cancel(self)
            self._scan_anim = None
        if hasattr(self, "_scan_color"):
            self._scan_color.rgba = (0, 0, 0, 0)

    def _redraw(self, *_):
        from nova.ui.mode_card import chamfer_points, _mesh_from_polygon
        name = theme.name
        x, y, w, h = self.x, self.y, self.width, self.height
        if w <= 0 or h <= 0:
            return

        # Le fill (surface_light) sert au mesh comme au rect ; on masque l'inutilisé.
        self._fill.rgba = theme.get_rgba("surface_light")
        self._border.rgba = theme.get_rgba("glass_border")
        self._rect.pos = (-9999, -9999)
        self._rect.size = (0, 0)
        self._mesh.vertices = []
        self._mesh.indices = []
        self._line.points = []
        self._line.rounded_rectangle = (0, 0, 0, 0, 0)

        if name == "cyberpunk":
            cut = dp(10)
            poly = chamfer_points(x, y, w, h, cut)
            verts, idx = _mesh_from_polygon(poly)
            self._mesh.vertices = verts
            self._mesh.indices = idx
            self._line.width = 1.6
            self._line.dash_length = 100000
            self._line.points = poly + poly[0:2]
        elif name == "undercover":
            self._rect.pos = (x, y)
            self._rect.size = (w, h)
            self._rect.radius = [dp(2)]
            self._line.width = 1.0
            self._line.dash_length = dp(4)
            self._line.dash_offset = dp(3)
            self._line.rounded_rectangle = (x, y, w, h, dp(2))
        else:  # classic
            self._rect.pos = (x, y)
            self._rect.size = (w, h)
            self._rect.radius = [dp(12)]
            self._line.width = 1.1
            self._line.dash_length = 100000
            self._line.dash_offset = 0
            self._line.rounded_rectangle = (x, y, w, h, dp(12))

    def _on_theme(self, *_):
        self._fill.rgba = theme.get_rgba("surface_light")
        self._border.rgba = theme.get_rgba("glass_border")
        self.caption.color = theme.get_rgba("text_secondary")
        self._redraw()

    def on_press(self):
        self._border.rgba = theme.get_rgba("primary", 0.9)

    def on_release(self):
        self._border.rgba = theme.get_rgba("glass_border")
        if callable(self.on_launch):
            self.on_launch(self.app_id)


class NavButton(ButtonBehavior, Widget):
    """Bouton rond de la barre de navigation basse."""

    def __init__(self, icon_name, active=False, on_tap=None, **kwargs):
        super().__init__(**kwargs)
        self.on_tap = on_tap
        self.active = active
        self.size_hint = (None, 1)
        self.width = dp(48)

        with self.canvas.before:
            self._bg = Color(*self._bg_color())
            self._circle = RoundedRectangle()
        self.bind(pos=self._redraw, size=self._redraw)

        self.icon = MaterialIcon(icon_name, size=dp(22),
                                 color_key="background" if active else "text_secondary")
        self.add_widget(self.icon)
        self.bind(pos=self._place_icon, size=self._place_icon)
        theme.bind(on_theme_change=lambda *_a: self._refresh())

    def _bg_color(self):
        return theme.get_rgba("primary") if self.active else theme.get_rgba("surface_light", 0)

    def _redraw(self, *_):
        d = dp(44)  # zone tactile recommandee pour un usage au poignet
        self._circle.pos = (self.center_x - d / 2, self.center_y - d / 2)
        self._circle.size = (d, d)
        self._circle.radius = [d / 2]

    def _place_icon(self, *_):
        self.icon.center = self.center
        self.icon.size = self.size

    def _refresh(self):
        self._bg.rgba = self._bg_color()
        self.icon.color = theme.get_rgba("background" if self.active else "text_secondary")

    def on_release(self):
        if callable(self.on_tap):
            self.on_tap()


class HomeScreen(Screen):
    """Accueil complet façon Stitch."""

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "home")
        super().__init__(**kwargs)
        self.launcher = None
        self._clocks = []
        self.build_ui()
        self._clocks.append(Clock.schedule_interval(self.update_time, 1))
        self._clocks.append(Clock.schedule_interval(self.update_event, 60))
        self._clocks.append(Clock.schedule_interval(self.update_sensors, 15))
        self._clocks.append(Clock.schedule_interval(self.update_status, 10))
        self.update_sensors()
        self.update_status()

    # ------------------------------------------------------------------
    def build_ui(self):
        self.root = FloatLayout()

        with self.root.canvas.before:
            self._bg_color = Color(*theme.get_rgba("background"))
            self._bg = RoundedRectangle()
        self.root.bind(pos=self._redraw_bg, size=self._redraw_bg)
        theme.bind(on_theme_change=self._on_theme)

        # Colonne principale.
        # Les hauteurs sont en PROPORTIONS (size_hint_y) et non en pixels
        # fixes, pour respecter le rythme vertical de la maquette Stitch quel
        # que soit l'ecran (800x480 paysage, ou plus tard un autre format).
        self.column = BoxLayout(orientation="vertical", padding=dp(14),
                                spacing=dp(8),
                                size_hint=(1, 1), pos_hint={"x": 0, "y": 0})

        header = self._build_header()
        header.size_hint_y = 0.06          # bandeau NOVA + statut
        self.column.add_widget(header)

        clock = self._build_clock()
        clock.size_hint_y = 0.15           # bloc horloge
        clock.height = 0
        self.column.add_widget(clock)

        event = self._build_event_card()
        event.size_hint_y = 0.12           # carte « prochain evenement »
        self.column.add_widget(event)

        # Respiration avant la grille (reduite : les tuiles priment)
        self.column.add_widget(Widget(size_hint_y=0.015))

        # Grille d'applications : le coeur de l'ecran.
        # 3 colonnes, conforme a la maquette Stitch (code.html: grid-cols-3).
        self.apps_grid = GridLayout(cols=3, spacing=dp(10), size_hint=(1, 0.47))
        self.column.add_widget(self.apps_grid)

        sensors = self._build_sensor_line()
        sensors.size_hint_y = 0.06         # bandeau de mesures
        self.column.add_widget(sensors)

        # Respiration avant le dock
        self.column.add_widget(Widget(size_hint_y=0.02))

        navbar = self._build_navbar()
        navbar.size_hint_y = 0.10          # dock de navigation, en bas
        self.column.add_widget(navbar)

        self.root.add_widget(self.column)
        self.add_widget(self.root)
        self.update_time()

    def _build_header(self):
        """Ligne NOVA + statut, en haut."""
        bar = BoxLayout(size_hint=(1, 0.07), spacing=dp(8))

        brand = BoxLayout(size_hint=(0.5, 1), spacing=dp(6))
        self.brand_icon = MaterialIcon("bolt", size=dp(20), color_key="primary",
                                       size_hint=(None, 1), width=dp(22))
        brand_label = Label(text="NOVA", font_name=fonts.FONT_DISPLAY, bold=True,
                            font_size=dp(18), halign="left", valign="middle",
                            color=theme.get_rgba("text_primary"))
        brand_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        brand.add_widget(self.brand_icon)
        brand.add_widget(brand_label)
        bar.add_widget(brand)

        self.status_label = Label(
            text="", font_name=fonts.FONT_MONO, font_size=dp(11),
            halign="right", valign="middle", size_hint=(0.5, 1),
            markup=True,
            color=theme.get_rgba("text_secondary"))
        self.status_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        bar.add_widget(self.status_label)
        return bar

    def _build_clock(self):
        box = BoxLayout(orientation="vertical", size_hint=(1, 0.20), spacing=dp(2))
        # Horloge avec halo : la couleur suit le mode (rouge en cyberpunk)
        self.time_label = GlowLabel(
            text="00:00", font_name=fonts.FONT_DISPLAY_XL, font_size=dp(58),
            color=theme.get_rgba("primary"), glow_color=theme.get_rgba("primary"),
            halign="left", valign="bottom", size_hint=(1, 0.7))
        box.add_widget(self.time_label)
        self.date_label = Label(text="", font_name=fonts.FONT_MONO, font_size=dp(12),
                                halign="left", valign="top", size_hint=(1, 0.3),
                                color=theme.get_rgba("text_secondary"))
        self.date_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        box.add_widget(self.date_label)
        theme.bind(on_theme_change=lambda *_a: self._refresh_clock_color())
        return box

    def _refresh_clock_color(self):
        """L'horloge est rouge et halo rouge en cyberpunk, sinon primary."""
        if theme.name == "cyberpunk":
            col = theme.get_rgba("accent")   # #FF003C
        else:
            col = theme.get_rgba("primary")
        self.time_label.set_colors(col, col)
        self.date_label.color = theme.get_rgba("text_secondary")

    def _build_event_card(self):
        card = ModeCard(size_hint=(1, None), height=dp(62), radius=dp(14))
        self.event_card = card
        outer = BoxLayout(orientation="vertical", padding=[dp(12), dp(7)],
                          spacing=dp(4), size_hint=(1, 1), pos_hint={"x": 0, "y": 0})

        row = BoxLayout(spacing=dp(10), size_hint=(1, 1))

        self.event_icon = MaterialIcon("event_note", size=dp(24), color_key="primary",
                                       size_hint=(None, 1), width=dp(28))
        row.add_widget(self.event_icon)

        texts = BoxLayout(orientation="vertical", size_hint=(1, 1))
        self.event_caption = Label(text="PROCHAIN ÉVÉNEMENT", font_name=fonts.FONT_MONO,
                                   font_size=dp(9), halign="left", valign="bottom",
                                   size_hint=(1, 0.42), color=theme.get_rgba("text_secondary"))
        self.event_caption.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.event_label = Label(text="Aucun événement prévu", font_name=fonts.FONT_BODY,
                                 font_size=dp(14), halign="left", valign="top",
                                 size_hint=(1, 0.58), color=theme.get_rgba("text_primary"),
                                 max_lines=1, shorten=True, shorten_from="right")
        self.event_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        texts.add_widget(self.event_caption)
        texts.add_widget(self.event_label)
        row.add_widget(texts)

        self.event_chevron = MaterialIcon("chevron_right", size=dp(22),
                                          color_key="text_secondary",
                                          size_hint=(None, 1), width=dp(22))
        row.add_widget(self.event_chevron)
        outer.add_widget(row)

        # Barre de progression "mission" (visible surtout en cyberpunk)
        self.progress_track = Widget(size_hint=(1, None), height=dp(3))
        with self.progress_track.canvas:
            self._prog_bg = Color(*theme.get_rgba("text_secondary", 0.15))
            self._prog_bg_rect = RoundedRectangle(radius=[dp(1.5)])
            self._prog_col = Color(*theme.get_rgba("error"))
            self._prog_rect = RoundedRectangle(radius=[dp(1.5)])
        self.progress_track.bind(pos=self._redraw_progress, size=self._redraw_progress)
        outer.add_widget(self.progress_track)

        card.add_widget(outer)
        theme.bind(on_theme_change=lambda *_a: self._refresh_event_style())
        self._refresh_event_style()
        return card

    def _redraw_progress(self, *_):
        t = self.progress_track
        self._prog_bg_rect.pos = t.pos
        self._prog_bg_rect.size = t.size
        self._prog_rect.pos = t.pos
        self._prog_rect.size = (t.width * 0.66, t.height)   # rempli aux 2/3

    def _refresh_event_style(self):
        """Accents de la carte événement selon le mode."""
        name = theme.name
        # La barre de mission n'a de sens qu'en cyberpunk
        show_progress = (name == "cyberpunk")
        self.progress_track.height = dp(3) if show_progress else 0
        self.progress_track.opacity = 1 if show_progress else 0

        if name == "cyberpunk":
            # bloc « mission » : libellé NEXT_OBJECTIVE, tout en rouge, cadre rouge
            self.event_caption.text = "NEXT_OBJECTIVE"
            self.event_caption.color = theme.get_rgba("accent")   # #FF003C
            self.event_icon.color = theme.get_rgba("accent")
            self.event_chevron.color = theme.get_rgba("accent")
            self._prog_col.rgba = theme.get_rgba("accent")
            # forcer la bordure de la carte en rouge (au lieu du jaune du mode)
            self.event_card.set_border_override(theme.get_rgba("accent"))
        elif name == "undercover":
            self.event_caption.text = "> PROCHAIN_EVENEMENT"
            self.event_caption.color = theme.get_rgba("text_secondary")
            self.event_icon.color = theme.get_rgba("text_secondary")
            self.event_chevron.color = theme.get_rgba("text_secondary")
            self.event_card.set_border_override(None)
        else:  # classic
            self.event_caption.text = "PROCHAIN ÉVÉNEMENT"
            self.event_caption.color = theme.get_rgba("text_secondary")
            self.event_icon.color = theme.get_rgba("primary")
            self.event_chevron.color = theme.get_rgba("text_secondary")
            self.event_card.set_border_override(None)
        self._prog_bg.rgba = theme.get_rgba("text_secondary", 0.15)
        self._redraw_progress()

    def _build_navbar(self):
        bar = BoxLayout(size_hint=(1, None), height=dp(52), spacing=dp(6),
                        padding=[dp(30), dp(6)])
        bar.add_widget(Widget())
        self.nav_home = NavButton("home", active=True)
        self.nav_explore = NavButton("explore", on_tap=lambda: self._open("maps"))
        self.nav_eq = NavButton("graphic_eq", on_tap=lambda: self._open("radio"))
        self.nav_palette = NavButton("palette", on_tap=self.cycle_mode)
        for b in (self.nav_home, self.nav_explore, self.nav_eq, self.nav_palette):
            bar.add_widget(b)
            bar.add_widget(Widget(size_hint_x=None, width=dp(4)))
        bar.add_widget(Widget())
        return bar

    def _build_sensor_line(self):
        """Ligne de capteurs : TEMP_EXT · HUM_IND · AQI_LVL (façon maquette)."""
        line = BoxLayout(size_hint=(1, None), height=dp(22), spacing=dp(4))

        def cell(label):
            box = BoxLayout(spacing=dp(4))
            cap = Label(text=label, font_name=fonts.FONT_MONO, font_size=dp(9),
                        halign="right", valign="middle", size_hint=(0.55, 1),
                        color=theme.get_rgba("text_secondary"))
            cap.bind(size=lambda w, s: setattr(w, "text_size", s))
            val = Label(text="--", font_name=fonts.FONT_MONO, font_size=dp(11),
                        bold=True, halign="left", valign="middle", size_hint=(0.45, 1),
                        color=theme.get_rgba("primary"))
            val.bind(size=lambda w, s: setattr(w, "text_size", s))
            box.add_widget(cap)
            box.add_widget(val)
            return box, val

        temp_box, self.sensor_temp = cell("TEMP_EXT")
        hum_box, self.sensor_hum = cell("HUM_IND")
        aqi_box, self.sensor_aqi = cell("AQI_LVL")
        line.add_widget(temp_box)
        line.add_widget(hum_box)
        line.add_widget(aqi_box)

        theme.bind(on_theme_change=lambda *_a: self._refresh_sensor_colors())
        return line

    def _refresh_sensor_colors(self):
        for val in (getattr(self, "sensor_temp", None), getattr(self, "sensor_hum", None),
                    getattr(self, "sensor_aqi", None)):
            if val is not None:
                val.color = theme.get_rgba("primary")

    def update_sensors(self, _dt=None):
        """Lit les capteurs (réels si dispo, sinon simulation)."""
        try:
            from apps.sensors.app import SensorsApp  # source de vérité si présente
        except Exception:
            SensorsApp = None
        # Valeurs par défaut (simulation PC) — remplacées par le BME280 sur le Pi
        temp, hum, aqi = 24.5, 42, "LOW"
        try:
            from nova.utils.platform_utils import is_raspberry_pi
            if is_raspberry_pi():
                # Emplacement pour la lecture réelle du BME280 (à brancher plus tard)
                pass
        except Exception:
            pass
        if hasattr(self, "sensor_temp"):
            self.sensor_temp.text = "{:.1f}°C".format(temp)
            self.sensor_hum.text = "{}%".format(hum)
            self.sensor_aqi.text = aqi

    def update_status(self, _dt=None):
        """Statut WIFI + Bluetooth + batterie en haut à droite (texte, charte Undercover)."""
        from nova.utils.platform_utils import wifi_state, bluetooth_state

        # "none" (aucune interface, ex. sur PC de dev) est traité comme actif
        # pour ne pas afficher une croix rouge trompeuse en simulation.
        wifi_up = wifi_state() != "down"
        bt_up = bluetooth_state() != "down"
        wifi = "4/4" if wifi_up else "0/4"
        bt = "ON" if bt_up else "OFF"
        # Batterie
        try:
            from nova.power_manager import get_power_manager
            bat = int(get_power_manager().get_battery_level())
        except Exception:
            bat = 82
        sec = theme.get_color("text_secondary").lstrip("#") + "ff"
        pri = theme.get_color("primary").lstrip("#") + "ff"
        self.status_label.text = (
            "[color={sec}]WIFI[/color] [color={pri}]{wifi}[/color]  "
            "[color={sec}]BT[/color] [color={pri}]{bt}[/color]  "
            "[color={sec}]BAT[/color] [color={pri}]{bat}%[/color]"
        ).format(sec=sec, pri=pri, wifi=wifi, bt=bt, bat=bat)

    # ------------------------------------------------------------------
    def bind_launcher(self, launcher):
        self.launcher = launcher
        self.populate_apps(launcher.get_app_info())

    def populate_apps(self, apps_info):
        self.apps_grid.clear_widgets()
        apps = list(apps_info or [])
        self._tiles = []
        for app in apps:
            # icon_safe previent en console si une icone manque
            icon_name = ICON_BY_APP.get(app["id"], "settings")
            if not fonts.has_icon(icon_name):
                fonts.icon_safe(icon_name)          # trace l'anomalie
                icon_name = "settings"
            tile = AppTile(app["id"], app.get("name", app["id"]).upper(),
                           icon_name, on_launch=self._open)
            self.apps_grid.add_widget(tile)
            self._tiles.append(tile)

    def animate_tiles_in(self):
        """Fait apparaître les tuiles en cascade (fondu + léger glissement)."""
        if not animations_enabled():
            return
        for i, tile in enumerate(getattr(self, "_tiles", [])):
            tile.opacity = 0
            Animation.cancel_all(tile, "opacity")
            anim = Animation(opacity=1, duration=0.28, t="out_quad")
            Clock.schedule_once(lambda dt, t=tile, a=anim: a.start(t), 0.05 * i)

    def _open(self, app_id):
        if self.launcher is not None:
            self.launcher.launch_app(app_id)

    # ------------------------------------------------------------------
    def cycle_mode(self):
        """Fait tourner Classic -> Cyberpunk -> Undercover, avec transition."""
        try:
            idx = MODE_CYCLE.index(theme.name)
        except ValueError:
            idx = 0
        nxt = MODE_CYCLE[(idx + 1) % len(MODE_CYCLE)]

        if animations_enabled():
            # bref flash de fondu sur la colonne pour marquer le changement
            Animation.cancel_all(self.column, "opacity")
            fade = Animation(opacity=0.45, duration=0.12) + Animation(opacity=1, duration=0.22)
            fade.start(self.column)
            Clock.schedule_once(lambda dt: theme.set_theme(nxt), 0.12)
        else:
            theme.set_theme(nxt)
        print("[nova] mode :", nxt)

    def start_clock_pulse(self):
        """Pulsation lente et discrète de l'horloge (respiration lumineuse)."""
        if not animations_enabled():
            return
        main = getattr(self.time_label, "main", self.time_label)
        Animation.cancel_all(main, "opacity")
        pulse = (Animation(opacity=0.82, duration=1.6, t="in_out_sine")
                 + Animation(opacity=1.0, duration=1.6, t="in_out_sine"))
        pulse.repeat = True
        pulse.start(main)

    # ------------------------------------------------------------------
    def update_time(self, _dt=None):
        now = datetime.now()
        self.time_label.set_text(now.strftime("%H:%M"))
        self.date_label.text = "{} {} {}".format(
            DAYS_FR[now.weekday()], now.day, MONTHS_FR[now.month - 1])

    def update_event(self, _dt=None):
        try:
            from apps.calendar import storage
            events = storage.get_today_events()
        except Exception:
            return
        now = datetime.now().strftime("%H:%M")
        for event in events:
            if event["event_time"] >= now:
                self.event_label.text = "{} — {}".format(event["title"], event["event_time"])
                return
        self.event_label.text = "Aucun événement prévu"

    # ------------------------------------------------------------------
    def _redraw_bg(self, *_):
        self._bg.pos = self.root.pos
        self._bg.size = self.root.size

    def _on_theme(self, *_):
        self._bg_color.rgba = theme.get_rgba("background")
        # le markup couleur du statut est figé : le régénérer au changement de mode
        if hasattr(self, "status_label"):
            self.update_status()

    def on_pre_enter(self, *_args):
        self.update_time()
        self.update_event()
        # Prépare le fondu d'apparition
        if animations_enabled():
            self.root.opacity = 0

    def on_enter(self, *_args):
        if animations_enabled():
            Animation.cancel_all(self.root, "opacity")
            Animation(opacity=1, duration=0.3, t="out_quad").start(self.root)
            self.animate_tiles_in()
            self.start_clock_pulse()
            self.start_ai_scan()

    # ------------------------------------------------------------------
    # Balayage de l'icone AI : une ligne descend du haut vers le bas,
    # en boucle. Coupe sur Raspberry Pi via animations_enabled().
    # ------------------------------------------------------------------
    def start_ai_scan(self, intervalle=2.6):
        """Lance le balayage repete sur la tuile de l'assistant."""
        self.stop_ai_scan()
        self._ai_scan_clock = Clock.schedule_interval(self._ai_scan_step,
                                                      intervalle)
        self._ai_scan_step(0)      # premier passage immediat

    def stop_ai_scan(self):
        """Arrete le balayage."""
        clk = getattr(self, "_ai_scan_clock", None)
        if clk is not None:
            clk.cancel()
            self._ai_scan_clock = None
        tuile = self._ai_tile()
        if tuile is not None:
            tuile.stop_scan()

    def _ai_tile(self):
        """Renvoie la tuile de l'assistant (AI), ou None."""
        for w in self.apps_grid.children:
            if getattr(w, "app_id", None) == "assistant":
                return w
        return None

    def _ai_scan_step(self, _dt):
        tuile = self._ai_tile()
        if tuile is not None:
            tuile.scan()

    def on_leave(self, *_args):
        self.stop_ai_scan()

    def on_cleanup(self):
        self.stop_ai_scan()
        for c in self._clocks:
            c.cancel()
        self._clocks = []
