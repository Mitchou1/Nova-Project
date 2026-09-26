#!/usr/bin/env python3
"""Audit automatique de l'interface NOVA (écran 800x480, tactile).

Usage (racine du projet, venv activé) :
    python scripts/audit_ui.py [classic|cyberpunk|undercover] [dossier_captures]

Lance NOVA dans le thème demandé, affiche chaque écran, capture une image
et mesure chaque élément interactif (boutons, interrupteurs, curseurs,
champs de saisie). Signale :
  - CIBLE  : zone tactile de moins de 44 x 44 px (inutilisable au doigt)
  - HORS   : élément (en partie) hors de l'écran
  - CHEVAU : deux éléments interactifs qui se chevauchent
  - ETIRE  : bouton à icône seule déformé (ex. étiré par un BoxLayout)
  - ICONE  : icône inconnue de la police (bouton vide ou carré vide)
  - TEXTE  : texte plus large que son widget (coupé ou qui déborde)
Écrit un rapport JSON à côté des captures. C'est un outil de diagnostic :
code de sortie 0 dans tous les cas.
"""

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "software"))

THEME = sys.argv[1] if len(sys.argv) > 1 else "classic"
SORTIE = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "data", "logs", "audit_ui")
os.makedirs(SORTIE, exist_ok=True)

from nova.utils.config_loader import get_config                 # noqa: E402
get_config().set("theme", THEME, save=False)     # thème du test, sans l'enregistrer

import nova.main as nova_main                                    # noqa: E402
from kivy.clock import Clock                                     # noqa: E402
from kivy.core.window import Window                              # noqa: E402
from kivy.uix.behaviors import ButtonBehavior                    # noqa: E402
from kivy.uix.label import Label                                 # noqa: E402
from kivy.uix.screenmanager import NoTransition                  # noqa: E402
from kivy.uix.scrollview import ScrollView                       # noqa: E402
from kivy.uix.slider import Slider                               # noqa: E402
from kivy.uix.switch import Switch                               # noqa: E402
from kivy.uix.textinput import TextInput                         # noqa: E402
from nova import fonts                                           # noqa: E402

MIN_CIBLE = 44
INTERACTIFS = (ButtonBehavior, Switch, Slider, TextInput)
GLYPHES_CONNUS = set(fonts.ICONS.values())


def rect(w):
    x, y = w.to_window(w.x, w.y)
    return x, y, w.width, w.height


def nom(w):
    txt = getattr(w, "text", "") or ""
    ico = getattr(w, "icon", "") or ""
    txt, ico = (v if isinstance(v, str) else type(v).__name__ for v in (txt, ico))
    etiquette = (txt or ico).replace("\n", " ")[:24]
    return "{}{}".format(type(w).__name__, " «{}»".format(etiquette) if etiquette else "")


# Attention : le parent de la fenêtre Kivy est la fenêtre elle-même ; toute
# remontée de parents doit s'arrêter sur Window, sinon elle boucle sans fin.
def dans_scrollview(w):
    p = w.parent
    while p is not None and p is not Window:
        if isinstance(p, ScrollView):
            return p
        p = p.parent
    return None


def visible(w):
    p = w
    while p is not None and p is not Window:
        if getattr(p, "opacity", 1) <= 0.01:
            return False
        p = p.parent
    return w.get_root_window() is not None and w.width > 1 and w.height > 1


def intersection(a, b):
    dx = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    dy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return dx * dy if dx > 0 and dy > 0 else 0


def ancetre(a, b):
    p = b.parent
    while p is not None and p is not Window:
        if p is a:
            return True
        p = p.parent
    return False


def auditer(racine):
    problemes = []
    interactifs = [w for w in racine.walk() if isinstance(w, INTERACTIFS) and visible(w)]
    for w in interactifs:
        x, y, lw, lh = rect(w)
        # Hors écran : dans une zone qui défile, c'est normal (on y accède
        # en faisant défiler) ; ailleurs, c'est un bouton inatteignable.
        if dans_scrollview(w) is None and (x < -1 or y < -1 or x + lw > Window.width + 1
                                           or y + lh > Window.height + 1):
            problemes.append(("HORS", nom(w), "x={:.0f} y={:.0f} {:.0f}x{:.0f}".format(x, y, lw, lh)))
        petit = lh < MIN_CIBLE if isinstance(w, Slider) else (lw < MIN_CIBLE or lh < MIN_CIBLE)
        if petit:
            problemes.append(("CIBLE", nom(w), "{:.0f}x{:.0f} px".format(lw, lh)))
        icone_seule = isinstance(getattr(w, "icon", ""), str) and getattr(w, "icon", "") \
            and not getattr(w, "text", "")
        if icone_seule and lh > 0 and not (0.5 <= lw / lh <= 2.0):
            problemes.append(("ETIRE", nom(w), "{:.0f}x{:.0f} px (ratio {:.1f})".format(lw, lh, lw / lh)))
        if getattr(w, "icon", "") and hasattr(w, "_resolve_icon_char") and not w._resolve_icon_char():
            problemes.append(("ICONE", nom(w), "icône « {} » inconnue : bouton vide".format(w.icon)))
    for i, a in enumerate(interactifs):
        for b in interactifs[i + 1:]:
            if ancetre(a, b) or ancetre(b, a):
                continue
            ra, rb = rect(a), rect(b)
            aire = intersection(ra, rb)
            plus_petite = min(ra[2] * ra[3], rb[2] * rb[3]) or 1
            if aire / plus_petite > 0.10:
                problemes.append(("CHEVAU", "{} / {}".format(nom(a), nom(b)),
                                  "{:.0f} % recouvert".format(100 * aire / plus_petite)))
    for w in racine.walk():
        if not isinstance(w, Label) or not visible(w) or not w.text:
            continue
        if w.font_name == fonts.FONT_ICON:
            inconnus = [c for c in w.text if c.strip() and c not in GLYPHES_CONNUS]
            if inconnus:
                problemes.append(("ICONE", nom(w), "glyphe(s) absent(s) : {}".format(
                    " ".join("U+{:04X}".format(ord(c)) for c in inconnus))))
            elif dans_scrollview(w) is None and w.font_size * 0.9 > w.height + 2:
                problemes.append(("ICONE", nom(w), "icône de {:.0f} px dans une case de {:.0f} px : coupée"
                                  .format(w.font_size, w.height)))
            continue
        # Police plus haute que sa case : avec text_size fixé, Kivy rogne la
        # texture au lieu de la laisser dépasser -> il faut comparer la police.
        if dans_scrollview(w) is None and w.font_size > w.height + 2 and "\n" not in w.text:
            problemes.append(("TEXTE", nom(w), "police {:.0f} px dans une case de {:.0f} px : coupé"
                              .format(w.font_size, w.height)))
        if w.shorten or w.texture_size[0] == 0:
            continue
        if dans_scrollview(w) is not None:
            continue
        largeur = w.text_size[0] if w.text_size[0] else w.width
        if w.texture_size[0] > largeur + 4:
            problemes.append(("TEXTE", nom(w), "texte {:.0f} px de large pour {:.0f} px".format(
                w.texture_size[0], largeur)))
        # Hauteur : un texte plus haut que sa case est coupé (cas des tuiles
        # de l'accueil, que la seule vérification de largeur ne voyait pas)
        if w.texture_size[1] > w.height + 6:
            problemes.append(("TEXTE", nom(w), "texte {:.0f} px de haut pour {:.0f} px".format(
                w.texture_size[1], w.height)))
    return problemes


app = nova_main.NovaApp()
rapport = {}


def demarrer(_dt):
    app.sm.transition = NoTransition()
    ecrans = list(app.sm.screen_names)
    print("[audit] thème {} — {} écrans : {}".format(THEME, len(ecrans), ", ".join(ecrans)))

    def suivant(i):
        if i >= len(ecrans):
            terminer()
            return
        app.sm.current = ecrans[i]

        def mesurer(_dt):
            nom_ecran = ecrans[i]
            Window.screenshot(os.path.join(SORTIE, "{}_{}.png".format(THEME, nom_ecran)))
            rapport[nom_ecran] = auditer(app.sm.get_screen(nom_ecran))
            Clock.schedule_once(lambda dt: suivant(i + 1), 0.1)
        Clock.schedule_once(mesurer, 1.2)
    suivant(0)


def terminer():
    chemin = os.path.join(SORTIE, "rapport_{}.json".format(THEME))
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=1)
    total = 0
    for ecran, problemes in rapport.items():
        print("\n■ {} ({} problème(s))".format(ecran, len(problemes)))
        for code, qui, detail in problemes:
            print("   {:<6} {:<42} {}".format(code, qui[:42], detail))
        total += len(problemes)
    print("\n[audit] {} problème(s) — rapport : {}".format(total, chemin))
    app.stop()


Clock.schedule_interval(lambda dt: setattr(app, "_last_touch", time.time()), 0.5)
Clock.schedule_once(demarrer, 2.5)
app.run()
