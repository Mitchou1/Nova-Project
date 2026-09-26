#!/usr/bin/env python3
"""Clavier virtuel NOVA (AZERTY) + remontée automatique du champ actif.

Pourquoi un clavier intégré : sur le Pi, c'était le clavier du SYSTÈME qui
s'affichait par-dessus la fenêtre. Kivy ne connaît ni sa présence ni sa
hauteur (Window.keyboard_height ne marche que sur Android/iOS) : impossible
de savoir de combien remonter le champ, qui restait caché dessous.
Un clavier dessiné par NOVA a une hauteur connue : le champ peut être
placé exactement au-dessus, et le clavier suit les 3 thèmes.

Branchement : Kivy crée ce clavier lui-même dès qu'un TextInput prend le
focus (mode « systemanddock » + Window.set_vkeyboard_class, voir main.py).
Il respecte le contrat du VKeyboard de Kivy — caractères via on_textinput,
touches spéciales via on_key_down — donc TOUS les champs existants
l'utilisent sans aucune modification, dans toutes les apps.

Remontée : à l'ouverture, le gestionnaire d'écrans glisse vers le haut
juste assez pour que le bas du champ actif soit au-dessus du clavier ;
il redescend à la fermeture. Les couches de veille/alerte ne bougent pas.
"""

import time

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.event import EventDispatcher
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button

from nova import fonts
from nova.ui.theme import theme_manager

# Dispositions : (texte, largeur relative). Un texte « :nom » est une touche
# spéciale. 10 unités par rangée : ~76 px par touche sur 800 px, et ~46 px
# de haut, au-dessus du minimum tactile de 44 px.
DISPOSITIONS = {
    "lettres": [
        [(c, 1) for c in "azertyuiop"],
        [(c, 1) for c in "qsdfghjklm"],
        [(":shift", 1.5)] + [(c, 1) for c in "wxcvbn'"] + [(":backspace", 1.5)],
        [(":chiffres", 1.5), ("é", 1), ("è", 1), ("à", 1), (":espace", 2.5),
         ("ç", 1), (",", 1), (":entree", 1)],
    ],
    "chiffres": [
        [(c, 1) for c in "1234567890"],
        [(c, 1) for c in "@#€%&-+()/"],
        [(c, 1) for c in ".,;:!?\"*="] + [(":backspace", 1)],
        [(":lettres", 1.5), ("ù", 1), ("ê", 1), ("â", 1), (":espace", 2.5),
         ("ô", 1), (":masquer", 1), (":entree", 1)],
    ],
}

# Touche spéciale -> (icône Material, texte si pas d'icône)
_SPECIALES = {
    ":shift": ("shift", None), ":backspace": ("backspace", None),
    ":entree": ("keyboard_return", None), ":espace": ("space_bar", None),
    ":masquer": ("keyboard_hide", None),
    ":chiffres": (None, "?123"), ":lettres": (None, "ABC"),
}

DOUBLE_APPUI = 0.35       # s : double appui sur Maj = verrouillage majuscules
DELAI_REPETITION = 0.45   # s avant répétition de la touche effacer maintenue
PAS_REPETITION = 0.06


def _est_speciale(code):
    return code.startswith(":") and len(code) > 1


class _Decalage(EventDispatcher):
    """Décalage vertical (px) appliqué à la zone qui remonte. Animé par
    kivy.animation, puis converti en pos_hint : la zone est placée par un
    FloatLayout, qui écraserait un simple changement de y."""
    valeur = NumericProperty(0)


_decalage = _Decalage()
_cible_remontee = [None]


def _appliquer_decalage(_inst, valeur):
    cible = _cible_remontee[0]
    if cible is None or cible.parent is None or not cible.parent.height:
        return
    hint = dict(cible.pos_hint or {})
    hint.pop("top", None)
    hint.pop("center_y", None)
    hint["y"] = valeur / float(cible.parent.height)
    cible.pos_hint = hint


_decalage.bind(valeur=_appliquer_decalage)


def set_lift_target(widget):
    """Déclare la zone à faire remonter (le ScreenManager de NOVA).

    Changer d'écran ferme le clavier : sinon il restait ouvert pour un
    champ devenu invisible (ex. bouton RETOUR pendant la saisie).
    """
    _cible_remontee[0] = widget
    if hasattr(widget, "current"):
        widget.bind(current=lambda *_a: Window.release_all_keyboards())


def decalage_actuel():
    return _decalage.valeur


def _animer_decalage(valeur):
    Animation.cancel_all(_decalage)
    Animation(valeur=valeur, d=0.2, t="out_cubic").start(_decalage)


class _Touche(Button):
    code = ObjectProperty(None)


class NovaKeyboard(BoxLayout):
    """Clavier docké en bas de l'écran, compatible VKeyboard de Kivy."""

    __events__ = ("on_key_down", "on_key_up", "on_textinput")

    # Attributs lus/écrits par kivy.core.window.WindowBase.request_keyboard
    target = ObjectProperty(None, allownone=True)
    callback = ObjectProperty(None, allownone=True)
    docked = BooleanProperty(True)
    # Lu par Window.keyboard_height (height * scale) à CHAQUE toucher : le
    # VKeyboard d'origine est un Scatter qui l'a ; sans lui, le premier
    # vrai toucher faisait planter NOVA (AttributeError trouvé en test).
    scale = NumericProperty(1.0)
    maj = BooleanProperty(False)
    verr_maj = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.padding = [dp(4), dp(6), dp(4), dp(6)]
        self.spacing = dp(5)
        self._disposition = "lettres"
        self._dernier_maj = 0.0
        self._repetition = None
        self._ouvert = False
        # Fenêtres surgissantes remontées : {popup: y d'origine}
        self._zones_libres = {}
        with self.canvas.before:
            Color(*theme_manager.get_with_alpha("background", 0.97))
            self._fond = Rectangle(pos=self.pos, size=self.size)
            Color(*theme_manager.get_with_alpha("primary", 0.6))
            self._trait = Rectangle(pos=self.pos, size=(self.width, dp(1)))
        self.bind(pos=self._maj_fond, size=self._maj_fond)
        Window.bind(size=self._ajuster_taille)
        self._ajuster_taille()
        self._construire()

    # --- géométrie --------------------------------------------------------
    def _ajuster_taille(self, *_a):
        self.width = Window.width
        # 45 % de l'écran au plus : 216 px sur l'écran 5" (800x480)
        self.height = min(dp(216), Window.height * 0.45)

    def _maj_fond(self, *_a):
        self._fond.pos, self._fond.size = self.pos, self.size
        self._trait.pos = (self.x, self.top - dp(1))
        self._trait.size = (self.width, dp(1))

    # --- construction des touches -----------------------------------------
    def _couleur_repos(self, code):
        return theme_manager.get_with_alpha("surface", 0.6 if _est_speciale(code) else 0.95)

    def _construire(self):
        self.clear_widgets()
        self._touches_lettres = []
        for rangee in DISPOSITIONS[self._disposition]:
            ligne = BoxLayout(spacing=dp(5))
            for code, largeur in rangee:
                icone, etiquette = _SPECIALES.get(code, (None, None))
                touche = _Touche(
                    code=code, size_hint_x=largeur,
                    background_normal="", background_down="",
                    background_color=self._couleur_repos(code),
                    color=theme_manager.get_color(
                        "primary" if _est_speciale(code) else "text"),
                    font_size=dp(22) if icone else dp(19),
                    bold=not icone,
                )
                if icone and fonts.has_icon(icone):
                    touche.font_name = fonts.FONT_ICON
                    touche.text = fonts.icon(icone)
                else:
                    touche.text = etiquette or code
                    if not _est_speciale(code):
                        self._touches_lettres.append(touche)
                touche.bind(on_press=self._appui, on_release=self._relache)
                ligne.add_widget(touche)
            self.add_widget(ligne)
        self._maj_etiquettes()

    def _maj_etiquettes(self, *_a):
        haut = self.maj or self.verr_maj
        for t in self._touches_lettres:
            t.text = t.code.upper() if haut else t.code
        for ligne in self.children:
            for t in ligne.children:
                if t.code == ":shift":
                    t.text = fonts.icon("keyboard_capslock" if self.verr_maj else "shift")
                    t.color = theme_manager.get_color("primary" if haut else "text_secondary")

    def on_maj(self, *_a):
        self._maj_etiquettes()

    def on_verr_maj(self, *_a):
        self._maj_etiquettes()

    # --- saisie -----------------------------------------------------------
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            # Sans ceci, Kivy retire le focus du champ après CHAQUE toucher
            # hors de lui (FocusBehavior) : taper une lettre fermerait le
            # clavier. Le toucher est aussi « consommé » : il n'atteint pas
            # les widgets situés sous le clavier.
            FocusBehavior.ignored_touch.append(touch)
            super().on_touch_down(touch)
            return True
        return super().on_touch_down(touch)

    def _appui(self, touche):
        code = touche.code
        touche.background_color = theme_manager.get_with_alpha("primary", 0.35)
        if code == ":backspace":
            self._touche_speciale("backspace")
            self._repetition = Clock.schedule_once(self._debut_repetition,
                                                   DELAI_REPETITION)
        elif code == ":entree":
            self._touche_speciale("enter")
        elif code == ":espace":
            self.dispatch("on_textinput", " ")
        elif code == ":shift":
            maintenant = time.time()
            if maintenant - self._dernier_maj < DOUBLE_APPUI:
                self.verr_maj, self.maj = True, False
            elif self.verr_maj:
                self.verr_maj = False
            else:
                self.maj = not self.maj
            self._dernier_maj = maintenant
        elif code in (":chiffres", ":lettres"):
            self._disposition = code[1:]
            # reconstruit après l'événement : on ne détruit pas la touche
            # en plein traitement de son propre appui
            Clock.schedule_once(lambda dt: self._construire(), 0)
        elif code == ":masquer":
            if self.target is not None:
                self.target.focus = False
        else:
            car = code.upper() if (self.maj or self.verr_maj) else code
            self.dispatch("on_textinput", car)
            if self.maj:            # Maj simple : une seule lettre
                self.maj = False

    def _relache(self, touche):
        touche.background_color = self._couleur_repos(touche.code)
        if self._repetition is not None:
            self._repetition.cancel()
            self._repetition = None

    def _debut_repetition(self, _dt):
        self._repetition = Clock.schedule_interval(
            lambda dt: self._touche_speciale("backspace"), PAS_REPETITION)

    def _touche_speciale(self, nom):
        self.dispatch("on_key_down", nom, None, [])
        self.dispatch("on_key_up", nom, None, [])

    def on_key_down(self, *_a):
        pass

    def on_key_up(self, *_a):
        pass

    def on_textinput(self, *_a):
        pass

    # --- apparition / remontée du champ -----------------------------------
    def setup_mode(self, *_a):
        """Appelé par Kivy à chaque demande de clavier (focus d'un champ)."""
        self._ajuster_taille()
        self.x = 0
        if not self._ouvert:
            # glisse depuis le bas de l'écran
            self._ouvert = True
            self.y = -self.height
            Animation.cancel_all(self, "y")
            Animation(y=0, d=0.18, t="out_cubic").start(self)
        # Après la mise en page : la position du champ est alors à jour
        Clock.schedule_once(self._remonter_champ, 0)

    @staticmethod
    def _zone_de(champ):
        """Ce qui doit remonter pour ce champ : les écrans (ScreenManager),
        ou la fenêtre surgissante (Popup) qui le contient — une Popup est
        posée directement sur la fenêtre, elle ne bouge pas avec les écrans
        (cas de l'ajout de rendez-vous et de l'éditeur de Fichiers)."""
        w = champ
        while w.parent is not None and w.parent is not Window:
            if w is _cible_remontee[0]:
                return w
            w = w.parent
        return w if w.parent is Window else None

    def _remonter_champ(self, *_a):
        champ = self.target
        if champ is None or champ.get_root_window() is None:
            return
        zone = self._zone_de(champ)
        if zone is None:
            return
        # Décalage déjà appliqué à cette zone (elle peut être remontée)
        if zone is _cible_remontee[0]:
            deja = _decalage.valeur
        else:
            if zone not in self._zones_libres:
                self._zones_libres[zone] = zone.y
                # Une Popup se RECENTRE dès que sa position change
                # (ModalView.fbind('center', _align_center)) : notre
                # déplacement était annulé aussitôt. Recentrage suspendu
                # pendant la saisie, rétabli à la fermeture du clavier.
                if hasattr(zone, "_align_center"):
                    zone.funbind("center", zone._align_center)
            deja = zone.y - self._zones_libres[zone]
        _x, bas = champ.to_window(champ.x, champ.y)
        bas -= deja
        haut = bas + champ.height
        besoin = self.height + dp(8) - bas
        # Champ très haut (multiligne) : ne jamais pousser son haut hors écran
        besoin = max(0.0, min(besoin, max(0.0, Window.height - haut - dp(4))))
        if zone is _cible_remontee[0]:
            _animer_decalage(besoin)
        else:
            Animation.cancel_all(zone, "y")
            Animation(y=self._zones_libres[zone] + besoin, d=0.2, t="out_cubic").start(zone)

    def on_parent(self, _inst, parent):
        # Kivy retire le widget à la fermeture du clavier. Mais en passant
        # d'un champ à un autre, il le retire puis le remet aussitôt : on
        # attend une image avant de conclure à une vraie fermeture, sinon
        # l'écran redescendrait puis remonterait (clignotement).
        if parent is None:
            Clock.schedule_once(self._verifier_fermeture, 0)

    def _verifier_fermeture(self, _dt):
        if self.parent is None:
            self._ouvert = False
            Animation.cancel_all(self, "y")
            _animer_decalage(0)
            for zone, y_origine in self._zones_libres.items():
                Animation.cancel_all(zone, "y")
                anim = Animation(y=y_origine, d=0.2, t="out_cubic")
                if hasattr(zone, "_align_center"):
                    anim.bind(on_complete=lambda _a, z: z.fbind("center", z._align_center))
                if zone.parent is not None:      # popup encore ouverte
                    anim.start(zone)
                elif hasattr(zone, "_align_center"):
                    zone.fbind("center", zone._align_center)
            self._zones_libres.clear()
