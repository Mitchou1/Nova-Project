#!/usr/bin/env python3
"""Test de bout en bout du clavier virtuel NOVA, avec de VRAIS touchers.

Usage (racine du projet, venv activé ; ouvre la fenêtre NOVA ~15 s) :
    python scripts/test_clavier.py

Lance NOVA, puis simule des touchers réels (mêmes événements que l'écran
tactile, qui passent par toute la chaîne de Kivy) et vérifie :
  - le clavier apparaît au toucher d'un champ, et le champ remonte au-dessus ;
  - la frappe, la majuscule, l'effacement et le pavé chiffres ;
  - taper sur le clavier ne fait PAS perdre le focus au champ ;
  - un toucher hors du champ ferme le clavier et l'écran redescend ;
  - une fenêtre surgissante (ajout de rendez-vous) remonte aussi ;
  - changer d'écran ferme le clavier.
Code de sortie 0 si tout passe, 1 sinon.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "software"))

# « auto » n'active le clavier NOVA que sur la Pi : on le force pour le test
from nova.utils.config_loader import get_config                 # noqa: E402
_cfg = get_config()
_cfg.set("screen", dict(_cfg.get("screen", {}) or {}, virtual_keyboard=True), save=False)

import nova.main as nova_main                                    # noqa: E402
from kivy.base import EventLoop                                  # noqa: E402
from kivy.clock import Clock                                     # noqa: E402
from kivy.core.window import Window                              # noqa: E402
from kivy.input.motionevent import MotionEvent                   # noqa: E402
from kivy.uix.textinput import TextInput                         # noqa: E402

RESULTATS = []


def verifier(nom, condition, detail=""):
    RESULTATS.append(bool(condition))
    print("{} {}{}".format("OK  " if condition else "ÉCHEC", nom,
                           "  ({})".format(detail) if detail else ""))


class Toucher(MotionEvent):
    """Toucher d'écran simulé (même principe que kivy.tests.common)."""
    _n = [0]

    def __init__(self, x, y):
        Toucher._n[0] += 1
        super().__init__("Toucher", 1000 + Toucher._n[0],
                         {"x": x / (Window.width - 1.0), "y": y / (Window.height - 1.0)},
                         is_touch=True, type_id="touch")

    def depack(self, args):
        self.is_touch = True
        self.sx, self.sy = args["x"], args["y"]
        self.profile = ["pos"]
        super().depack(args)


def taper(x, y):
    t = Toucher(x, y)
    EventLoop._dispatch_input("begin", t)
    EventLoop._dispatch_input("end", t)


def clavier():
    return next((w for w in Window.children if type(w).__name__ == "NovaKeyboard"), None)


def taper_touche(code):
    for w in clavier().walk():
        if getattr(w, "code", None) == code:
            taper(*w.to_window(*w.center))
            return
    raise KeyError(code)


def bas(w):
    return w.to_window(w.x, w.y)[1]


app = nova_main.NovaApp()
etat = {}


def etapes():
    # Chaque étape attend la fin des animations (0,2 s) de la précédente.
    def ouvrir_assistant():
        # Sans animation : sinon le champ est encore en mouvement quand le
        # test le touche (démarrage plus chargé = animation plus lente).
        from kivy.uix.screenmanager import NoTransition
        app.sm.transition = NoTransition()
        app.sm.current = "assistant"

    def toucher_champ():
        etat["champ"] = next(w for w in app.sm.get_screen("assistant").walk()
                             if isinstance(w, TextInput))
        etat["bas_initial"] = bas(etat["champ"])
        taper(*etat["champ"].to_window(*etat["champ"].center))

    def taper_texte():
        kb = clavier()
        verifier("le clavier apparaît au toucher du champ", kb is not None)
        verifier("le champ est remonté au-dessus du clavier",
                 kb and bas(etat["champ"]) >= kb.height,
                 "bas du champ {:.0f} px, clavier {:.0f} px".format(
                     bas(etat["champ"]), kb.height if kb else 0))
        verifier("touches d'au moins 44 px de haut",
                 kb and min(w.height for w in kb.walk() if getattr(w, "code", None)) >= 44)
        for c in [":shift", "b", "o", "n", "j", "o", "u", "r", ":espace", "n", "o",
                  "v", "a", ":chiffres"]:
            taper_touche(c)

    def taper_chiffres():
        for c in ["1", "2", ":backspace", ":lettres"]:
            taper_touche(c)

    def verifier_texte():
        verifier("frappe, majuscule, chiffres et effacement",
                 etat["champ"].text == "Bonjour nova1", repr(etat["champ"].text))
        verifier("taper sur le clavier garde le focus du champ", etat["champ"].focus)
        taper(Window.width / 2, Window.height - 5)       # toucher hors du champ

    def verifier_fermeture():
        verifier("un toucher hors du champ ferme le clavier", clavier() is None)
        verifier("l'écran redescend à la fermeture",
                 abs(bas(etat["champ"]) - etat["bas_initial"]) < 2,
                 "{:.0f} px au lieu de {:.0f}".format(bas(etat["champ"]), etat["bas_initial"]))
        app.sm.current = "calendar"

    def ouvrir_popup():
        app.sm.get_screen("calendar")._show_add(None)

    def toucher_champ_popup():
        popup = next(w for w in Window.children if type(w).__name__ == "AddEventPopup")
        etat["popup"], etat["popup_y"] = popup, popup.y
        champ = min((w for w in popup.walk() if isinstance(w, TextInput)), key=bas)
        etat["champ_popup"] = champ
        taper(*champ.to_window(*champ.center))

    def verifier_popup():
        kb = clavier()
        verifier("le champ d'une fenêtre surgissante remonte aussi",
                 kb and bas(etat["champ_popup"]) >= kb.height,
                 "bas {:.0f} px, clavier {:.0f} px".format(
                     bas(etat["champ_popup"]), kb.height if kb else 0))
        etat["champ_popup"].focus = False

    def verifier_popup_fermee():
        verifier("la fenêtre surgissante revient à sa place",
                 abs(etat["popup"].y - etat["popup_y"]) < 2)
        etat["popup"].dismiss()
        app.sm.current = "assistant"

    def champ_puis_changement_ecran():
        taper(*etat["champ"].to_window(*etat["champ"].center))
        Clock.schedule_once(lambda dt: setattr(app.sm, "current", "home"), 0.5)

    def verifier_changement_ecran():
        verifier("changer d'écran ferme le clavier", clavier() is None)
        app.stop()

    return [ouvrir_assistant, toucher_champ, taper_texte, taper_chiffres,
            verifier_texte, verifier_fermeture, ouvrir_popup, toucher_champ_popup,
            verifier_popup, verifier_popup_fermee, champ_puis_changement_ecran,
            verifier_changement_ecran]


# pas de mise en veille pendant le test
Clock.schedule_interval(lambda dt: setattr(app, "_last_touch", time.time()), 0.5)
for i, etape in enumerate(etapes()):
    Clock.schedule_once(lambda dt, e=etape: e(), 2.0 + i * 0.8)
app.run()

print("\n{}/{} vérifications réussies".format(sum(RESULTATS), len(RESULTATS)))
sys.exit(0 if RESULTATS and all(RESULTATS) else 1)
