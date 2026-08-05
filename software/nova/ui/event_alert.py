#!/usr/bin/env python3
"""Alerte de rendez-vous NOVA (cahier des charges, Phase 5).

Quand l'heure d'un événement arrive, tout l'écran affiche le rendez-vous
avec son titre, son heure et ses détails. L'appareil vibre et annonce le
rendez-vous à voix haute. L'alerte reste affichée jusqu'à ce qu'on la ferme.
"""

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from nova import fonts
from nova.ui.theme import theme
from nova.ui.widgets import NeonButton


class EventAlert(FloatLayout):
    """Alerte plein écran pour un rendez-vous."""

    def __init__(self, on_close=None, **kwargs):
        super().__init__(**kwargs)
        self.on_close = on_close
        self.opacity = 0
        self.disabled = True
        self._evenement = None
        self._pulse_anim = None

        # Fond opaque
        with self.canvas.before:
            self._fond_color = Color(*theme.get_rgba("background", 0.97))
            self._fond = Rectangle()
            # Cadre d'alerte qui pulse
            self._cadre_color = Color(*theme.get_rgba("warning", 0.9))
            self._cadre = Line(width=dp(2.4))
        self.bind(pos=self._place, size=self._place)

        colonne = BoxLayout(orientation="vertical", spacing=dp(6),
                            padding=[dp(28), dp(24)],
                            size_hint=(1, 1), pos_hint={"x": 0, "y": 0})

        # Bandeau « RAPPEL » en label-caps
        self.bandeau = Label(
            text="R A P P E L", font_name=fonts.FONT_MONO, font_size=dp(11),
            color=theme.get_rgba("warning"),
            size_hint=(1, 0.10),
        )
        colonne.add_widget(self.bandeau)

        # Heure en gros (data-mono, charte NOVA)
        self.heure = Label(
            text="--:--", font_name=fonts.FONT_MONO, bold=True,
            font_size=dp(46),
            color=theme.get_rgba("primary"),
            size_hint=(1, 0.26),
        )
        colonne.add_widget(self.heure)

        # Titre du rendez-vous (Sora)
        self.titre = Label(
            text="", font_name=fonts.FONT_DISPLAY, bold=True, font_size=dp(22),
            color=theme.get_rgba("text_primary"),
            size_hint=(1, 0.20), halign="center", valign="middle",
        )
        self.titre.bind(size=lambda w, s: setattr(w, "text_size", s))
        colonne.add_widget(self.titre)

        # Détails (description, date)
        self.details = Label(
            text="", font_name=fonts.FONT_MONO, font_size=dp(12),
            color=theme.get_rgba("text_secondary"),
            size_hint=(1, 0.18), halign="center", valign="top",
        )
        self.details.bind(size=lambda w, s: setattr(w, "text_size", s))
        colonne.add_widget(self.details)

        # Etat technique (vibration/voix indisponibles) : sur un wearable
        # sans terminal, un print() seul est invisible pour l'utilisateur.
        self.tech_status = Label(
            text="", font_name=fonts.FONT_MONO, font_size=dp(9),
            color=theme.get_rgba("error"),
            size_hint=(1, 0.08), halign="center", valign="top", opacity=0,
        )
        self.tech_status.bind(size=lambda w, s: setattr(w, "text_size", s))
        colonne.add_widget(self.tech_status)

        # Bouton de fermeture (l'alerte reste tant qu'on ne ferme pas)
        barre = BoxLayout(size_hint=(1, 0.20), padding=[dp(40), dp(6)])
        self.bouton = NeonButton(text="J'AI COMPRIS", corner_radius=dp(2))
        self.bouton.bind(on_press=lambda *_a: self.close())
        barre.add_widget(self.bouton)
        colonne.add_widget(barre)

        self.add_widget(colonne)

    def _place(self, *_a):
        self._fond.pos = self.pos
        self._fond.size = self.size
        m = dp(6)
        self._cadre.rectangle = (self.x + m, self.y + m,
                                 max(1, self.width - m * 2),
                                 max(1, self.height - m * 2))

    # ------------------------------------------------------------------
    def show(self, evenement):
        """Affiche l'alerte, vibre et annonce le rendez-vous à voix haute.

        `evenement` : dict ou objet avec titre, heure, description, date.
        """
        self._evenement = evenement

        def champ(cle, defaut=""):
            if isinstance(evenement, dict):
                return evenement.get(cle, defaut)
            return getattr(evenement, cle, defaut)

        titre = champ("title") or champ("titre") or "Rendez-vous"
        heure = (champ("event_time") or champ("time") or "")[:5]
        description = champ("description", "")
        date = champ("event_date") or champ("date", "")

        self.heure.text = heure or "--:--"
        self.titre.text = titre
        bas = []
        if description:
            bas.append(description)
        if date:
            bas.append(date)
        self.details.text = "\n".join(bas) if bas else "—"
        self._pannes = []
        self.tech_status.text = ""
        self.tech_status.opacity = 0

        # Apparition
        self.disabled = False
        Animation.cancel_all(self, "opacity")
        Animation(opacity=1, duration=0.35, t="out_quad").start(self)
        self._start_pulse()

        # Vibration + voix, en parallèle de l'affichage
        self._vibrer()
        self._annoncer(titre, heure)

    def close(self, *_a):
        """Ferme l'alerte (uniquement sur action de l'utilisateur)."""
        self._stop_pulse()
        Animation.cancel_all(self, "opacity")
        anim = Animation(opacity=0, duration=0.25, t="out_quad")
        anim.bind(on_complete=lambda *_x: setattr(self, "disabled", True))
        anim.start(self)
        if self.on_close:
            self.on_close()

    # --- effets ---------------------------------------------------------
    def _start_pulse(self):
        """Le cadre d'alerte pulse pour attirer l'œil."""
        self._stop_pulse()

        def battement(_dt):
            vif = theme.get_rgba("warning", 0.95)
            doux = theme.get_rgba("warning", 0.25)
            self._cadre_color.rgba = (vif if self._cadre_color.rgba[3] < 0.5
                                      else doux)
        self._pulse_anim = Clock.schedule_interval(battement, 0.55)

    def _stop_pulse(self):
        if self._pulse_anim is not None:
            self._pulse_anim.cancel()
            self._pulse_anim = None
        self._cadre_color.rgba = theme.get_rgba("warning", 0.9)

    def _report_panne(self, libelle):
        """Affiche une panne (vibration/voix) : sur un wearable sans terminal,
        un print() seul ne serait jamais vu par l'utilisateur."""
        self._pannes.append(libelle)
        self.tech_status.text = " · ".join(self._pannes)
        self.tech_status.opacity = 1

    def _vibrer(self, duree=600):
        """Fait vibrer l'appareil (moteur 3V sur le Pi)."""
        try:
            from nova.assistant_actions import _vibrate
            _vibrate({"duree": duree})
        except Exception as error:
            print("[alerte] vibration impossible :", error)
            Clock.schedule_once(lambda dt: self._report_panne("vibration indisponible"), 0)

    def _annoncer(self, titre, heure):
        """Annonce le rendez-vous à voix haute (Piper), sans figer l'écran."""
        phrase = "Rappel : {}".format(titre)
        if heure:
            phrase += " à {}".format(heure.replace(":", " heure "))

        def parler():
            try:
                from nova.ai_engine import get_engine
                if not get_engine().say(phrase):
                    Clock.schedule_once(
                        lambda dt: self._report_panne("voix indisponible"), 0)
            except Exception as error:
                print("[alerte] annonce vocale impossible :", error)
                Clock.schedule_once(
                    lambda dt: self._report_panne("voix indisponible"), 0)

        import threading
        threading.Thread(target=parler, daemon=True).start()

    # --- l'alerte bloque les contacts en dessous ------------------------
    def on_touch_down(self, touch):
        """L'alerte bloque les contacts en dessous — mais seulement visible.

        Invisible, elle doit laisser passer tous les contacts vers
        l'interface, sinon l'écran devient inutilisable.
        """
        if self.disabled or self.opacity <= 0.05:
            return False
        super().on_touch_down(touch)
        return True               # rien ne passe derriere l'alerte
