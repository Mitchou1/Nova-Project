#!/usr/bin/env python3
"""Classe de base de toutes les applications NOVA — style Stitch.

En-tête cohérent avec l'écran d'accueil : fond qui suit le mode, bouton retour
avec flèche Material, titre en Sora, icône Material de l'app. Le contenu propre
à chaque application se met dans self.content, comme avant — l'API ne change
pas, donc les six apps continuent de fonctionner sans modification.

Chaque application définit app_name, app_id, et app_icon. app_icon peut être :
  - un nom d'icône Material connu (ex. "radio", "explore") -> icône vectorielle
  - un emoji ou tout autre texte -> affiché tel quel (repli)
"""

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from nova import fonts
from nova.ui.theme import theme

# Icône Material par app (si app_icon n'est pas déjà un nom Material)
_APP_ICON_BY_ID = {
    "assistant": "smart_toy",
    "maps": "explore",
    "calendar": "event_note",
    "sensors": "settings_input_component",
    "radio": "radio",
    "settings": "settings",
}


class BackButton(ButtonBehavior, FloatLayout):
    """Bouton retour : flèche Material + « RETOUR », cadre discret."""

    def __init__(self, on_tap=None, **kwargs):
        super().__init__(**kwargs)
        self.on_tap = on_tap
        self.size_hint = (None, 1)
        self.width = dp(96)

        with self.canvas.before:
            self._fill = Color(*theme.get_rgba("surface_light"))
            self._rect = RoundedRectangle(radius=[dp(8)])
            self._bcol = Color(*theme.get_rgba("glass_border"))
            self._line = Line(width=1.0, rounded_rectangle=(0, 0, 0, 0, dp(8)))
        self.bind(pos=self._redraw, size=self._redraw)

        row = BoxLayout(spacing=dp(4), padding=[dp(8), 0],
                        size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self.arrow = Label(text=fonts.icon("arrow_back"), font_name=fonts.FONT_ICON,
                           font_size=dp(18), size_hint=(None, 1), width=dp(20),
                           color=theme.get_rgba("primary"))
        self.arrow.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.arrow.halign = "center"
        self.arrow.valign = "middle"
        self.caption = Label(text="RETOUR", font_name=fonts.FONT_MONO, font_size=dp(11),
                             halign="left", valign="middle",
                             color=theme.get_rgba("text_secondary"))
        self.caption.bind(size=lambda w, s: setattr(w, "text_size", s))
        row.add_widget(self.arrow)
        row.add_widget(self.caption)
        self.add_widget(row)

        theme.bind(on_theme_change=lambda *_a: self._refresh())

    def _redraw(self, *_):
        r = dp(2) if theme.name in ("cyberpunk", "undercover") else dp(8)
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._rect.radius = [r]
        self._line.rounded_rectangle = (self.x, self.y, self.width, self.height, r)
        if theme.name == "undercover":
            self._line.dash_length = dp(4)
            self._line.dash_offset = dp(3)
        else:
            self._line.dash_length = 100000
            self._line.dash_offset = 0

    def _refresh(self):
        self._fill.rgba = theme.get_rgba("surface_light")
        self._bcol.rgba = theme.get_rgba("glass_border")
        self.arrow.color = theme.get_rgba("primary")
        self.caption.color = theme.get_rgba("text_secondary")
        self._redraw()

    def on_press(self):
        self._bcol.rgba = theme.get_rgba("primary", 0.9)

    def on_release(self):
        self._bcol.rgba = theme.get_rgba("glass_border")
        if callable(self.on_tap):
            self.on_tap()


class BaseApp(Screen):
    """Écran d'application avec en-tête Stitch et zone de contenu."""

    app_name = "Application"
    app_icon = "•"
    app_id = "base"

    def __init__(self, **kwargs):
        kwargs.setdefault("name", self.app_id)
        super().__init__(**kwargs)
        self.content = None
        self.build_ui()

    def build_ui(self):
        root = FloatLayout()
        with root.canvas.before:
            self._bg_color = Color(*theme.get_rgba("background"))
            self._bg = RoundedRectangle()
        root.bind(pos=self._redraw_bg, size=self._redraw_bg)

        column = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10),
                           size_hint=(1, 1), pos_hint={"x": 0, "y": 0})

        # --- en-tête ---
        header = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(10))
        self.back_btn = BackButton(on_tap=self.go_home)
        header.add_widget(self.back_btn)

        title_box = BoxLayout(spacing=dp(8), size_hint=(1, 1))
        self.title_icon = Label(
            text=self._resolve_icon(), font_size=dp(24),
            size_hint=(None, 1), width=dp(28), halign="center", valign="middle",
            color=theme.get_rgba("primary"))
        if self._uses_material():
            self.title_icon.font_name = fonts.FONT_ICON
        self.title_icon.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.title_label = Label(
            text=self.app_name.upper(), font_name=fonts.FONT_DISPLAY, bold=True,
            font_size=dp(20), halign="left", valign="middle",
            color=theme.get_rgba("text_primary"))
        self.title_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        title_box.add_widget(self.title_icon)
        title_box.add_widget(self.title_label)
        header.add_widget(title_box)

        column.add_widget(header)

        # --- séparateur fin ---
        sep = Widget(size_hint=(1, None), height=dp(1))
        with sep.canvas:
            self._sep_color = Color(*theme.get_rgba("glass_border"))
            self._sep_rect = RoundedRectangle()
        sep.bind(pos=self._redraw_sep, size=self._redraw_sep)
        self._sep = sep
        column.add_widget(sep)

        # --- contenu de l'app ---
        self.content = BoxLayout(orientation="vertical", spacing=dp(8))
        column.add_widget(self.content)

        root.add_widget(column)
        self.add_widget(root)
        self._root = root

        theme.bind(on_theme_change=lambda *_a: self._refresh_chrome())

    def _resolve_icon(self):
        """Renvoie le glyphe Material de l'app (ou l'app_icon tel quel)."""
        # 1) app_icon est-il déjà un nom Material connu ?
        if fonts.has_icon(self.app_icon):
            return fonts.icon(self.app_icon)
        # 2) sinon, mapping par identifiant
        name = _APP_ICON_BY_ID.get(self.app_id)
        if name:
            return fonts.icon(name)
        # 3) repli : afficher app_icon tel quel (emoji, etc.)
        return self.app_icon

    def _uses_material(self):
        return fonts.has_icon(self.app_icon) or self.app_id in _APP_ICON_BY_ID

    # --- redraws ---------------------------------------------------------
    def _redraw_bg(self, *_):
        self._bg.pos = self._root.pos
        self._bg.size = self._root.size

    def _redraw_sep(self, *_):
        self._sep_rect.pos = self._sep.pos
        self._sep_rect.size = self._sep.size

    def _refresh_chrome(self):
        self._bg_color.rgba = theme.get_rgba("background")
        self._sep_color.rgba = theme.get_rgba("glass_border")
        self.title_label.color = theme.get_rgba("text_primary")
        if self._uses_material():
            self.title_icon.font_name = fonts.FONT_ICON
        self.title_icon.color = theme.get_rgba("primary")

    # --- navigation ------------------------------------------------------
    def go_home(self, *args):
        if self.manager is not None:
            self.manager.current = "home"

    def on_cleanup(self):
        return None


NovaApp = None
