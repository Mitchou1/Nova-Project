#!/usr/bin/env python3
"""App Terminal NOVA.

Un vrai terminal shell sur le Raspberry Pi, dans le style NOVA : on tape
n'importe quelle commande (ou on tape sur un raccourci) et la sortie
s'affiche en direct. Sert a manipuler le systeme et le dossier `software/`
sans sortir de l'interface — utile pour du depannage ou des taches rapides
(mises a jour, etat des conteneurs Docker, git, etc.).

`sudo` fonctionne seulement pour les commandes deja autorisees sans mot de
passe (NOPASSWD dans sudoers) : ce terminal n'a pas de champ pour saisir un
mot de passe, une commande qui en demande un restera bloquee jusqu'a l'arret.
"""

import os
import subprocess
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from apps.base_app import BaseApp
from nova import fonts
from nova.paths import ROOT_DIR
from nova.ui.theme import theme_manager
from nova.ui.widgets import NeonButton

# Raccourcis : etiquette -> commande shell (pas de sudo, pour rester utilisables
# sans mot de passe)
_RACCOURCIS = [
    ("IP", "hostname -I"),
    ("TEMP CPU", "vcgencmd measure_temp 2>/dev/null || "
                 "awk '{printf \"%.1f°C\\n\", $1/1000}' /sys/class/thermal/thermal_zone0/temp"),
    ("DISQUE", "df -h /"),
    ("MÉMOIRE", "free -h"),
    ("CONTENEURS", "docker ps --filter name=nova- "
                    "--format 'table {{.Names}}\\t{{.Status}}' 2>&1"),
    ("GIT STATUS", "git -C '{}' status --short --branch".format(ROOT_DIR)),
]

_MAX_LIGNES = 600      # limite la memoire/l'affichage sur une session longue


class CommandInput(TextInput):
    """Champ de saisie : flèches haut/bas pour rappeler l'historique."""

    def __init__(self, on_historique=None, **kwargs):
        super().__init__(**kwargs)
        self.on_historique = on_historique

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        code, nom = keycode
        if nom in ("up", "down") and self.on_historique:
            valeur = self.on_historique(nom)
            if valeur is not None:
                self.text = valeur
                self.cursor = (len(self.text), 0)
                return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)


class TerminalApp(BaseApp):
    """Terminal shell interactif sur le Raspberry Pi."""

    app_name = "Terminal"
    app_icon = "terminal"
    app_id = "terminal"

    def __init__(self, **kwargs):
        self.cwd = ROOT_DIR if ROOT_DIR.is_dir() else Path.home()
        self._lignes = []
        self._historique = []
        self._index_historique = None
        self._proc = None
        self._occupe = False
        super().__init__(**kwargs)

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ─── Barre de chemin ─────────────────────────────────────────
        barre = BoxLayout(size_hint=(0.95, None), height=dp(28),
                          pos_hint={"center_x": 0.5, "top": 0.965},
                          spacing=dp(8))
        self.chemin_label = Label(
            text="~", font_name=fonts.FONT_MONO, font_size=dp(11),
            color=theme_manager.get_color("primary"),
            size_hint=(1, 1), halign="left", valign="middle", shorten=True,
            shorten_from="left",
        )
        self.chemin_label.bind(
            size=lambda w, s: setattr(w, "text_size", (s[0], s[1])))
        barre.add_widget(self.chemin_label)

        self.temoin_occupe = Label(
            text="", font_name=fonts.FONT_MONO, font_size=dp(10),
            color=theme_manager.get_color("text_secondary"),
            size_hint=(None, 1), width=dp(90), halign="right", valign="middle")
        self.temoin_occupe.bind(
            size=lambda w, s: setattr(w, "text_size", (s[0], s[1])))
        barre.add_widget(self.temoin_occupe)

        btn_stop = NeonButton(icon="stop", accent="error", size_hint=(None, 1),
                              width=dp(40), corner_radius=dp(2))
        btn_stop.bind(on_press=lambda *_a: self.arreter())
        barre.add_widget(btn_stop)
        self.btn_stop = btn_stop
        self.btn_stop.disabled = True
        self.btn_stop.opacity = 0.4

        btn_effacer = NeonButton(icon="delete", size_hint=(None, 1),
                                 width=dp(40), corner_radius=dp(2))
        btn_effacer.bind(on_press=lambda *_a: self.effacer())
        barre.add_widget(btn_effacer)

        main.add_widget(barre)

        # ─── Sortie du terminal ───────────────────────────────────────
        self.scroll = ScrollView(size_hint=(0.95, 0.6),
                                 pos_hint={"center_x": 0.5, "top": 0.925},
                                 do_scroll_x=False)
        self.sortie = Label(
            text="", font_name=fonts.FONT_MONO, font_size=dp(11),
            color=theme_manager.get_color("text"),
            size_hint_y=None, halign="left", valign="top",
            markup=False,
        )
        self.sortie.bind(
            width=lambda w, v: setattr(w, "text_size", (v, None)),
            texture_size=lambda w, v: setattr(w, "height", max(v[1], self.scroll.height)))
        self.scroll.add_widget(self.sortie)
        main.add_widget(self.scroll)

        self._afficher(
            "NOVA Terminal — {}\n"
            "Tapez une commande et validez. « cd », « clear » fonctionnent. "
            "sudo sans mot de passe seulement.".format(ROOT_DIR))

        # ─── Raccourcis ────────────────────────────────────────────────
        defilement_raccourcis = ScrollView(size_hint=(0.95, None), height=dp(40),
                                           pos_hint={"center_x": 0.5},
                                           do_scroll_y=False, bar_width=0)
        ligne_raccourcis = BoxLayout(size_hint=(None, 1), spacing=dp(6))
        ligne_raccourcis.bind(minimum_width=ligne_raccourcis.setter("width"))
        for etiquette, commande in _RACCOURCIS:
            bouton = NeonButton(text=etiquette, size_hint=(None, 1), width=dp(108),
                                font_size=dp(10), corner_radius=dp(2))
            bouton.bind(on_press=lambda _b, c=commande: self.executer(c))
            ligne_raccourcis.add_widget(bouton)
        defilement_raccourcis.add_widget(ligne_raccourcis)
        main.add_widget(defilement_raccourcis)

        # ─── Ligne de commande ────────────────────────────────────────
        rangee = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(8))
        self.prompt_label = Label(
            text="$", font_name=fonts.FONT_MONO, font_size=dp(14),
            color=theme_manager.get_color("primary"),
            size_hint=(None, 1), width=dp(18))
        rangee.add_widget(self.prompt_label)

        self.entree = CommandInput(
            multiline=False, font_name=fonts.FONT_MONO, font_size=dp(13),
            background_color=theme_manager.get_with_alpha("surface", 0.9),
            foreground_color=theme_manager.get_color("text"),
            cursor_color=theme_manager.get_color("primary"),
            size_hint=(1, 1), on_historique=self._rappeler_historique,
        )
        self.entree.bind(on_text_validate=lambda *_a: self.executer(self.entree.text))
        rangee.add_widget(self.entree)

        self.btn_executer = NeonButton(icon="play_arrow", size_hint=(None, 1),
                                       width=dp(46), corner_radius=dp(2))
        self.btn_executer.bind(
            on_press=lambda *_a: self.executer(self.entree.text))
        rangee.add_widget(self.btn_executer)

        main.add_widget(rangee)

    # ------------------------------------------------------------------
    # Affichage
    # ------------------------------------------------------------------
    def _prompt_chemin(self):
        try:
            relatif = self.cwd.relative_to(ROOT_DIR)
            return "nova2" if str(relatif) == "." else "nova2/{}".format(relatif)
        except ValueError:
            return str(self.cwd)

    def _maj_prompt(self):
        self.chemin_label.text = self._prompt_chemin()

    def _afficher(self, texte):
        for ligne in texte.split("\n"):
            self._lignes.append(ligne)
        if len(self._lignes) > _MAX_LIGNES:
            self._lignes = self._lignes[-_MAX_LIGNES:]
        self.sortie.text = "\n".join(self._lignes)
        Clock.schedule_once(lambda *_a: setattr(self.scroll, "scroll_y", 0), 0)

    def effacer(self):
        self._lignes = []
        self.sortie.text = ""

    # ------------------------------------------------------------------
    # Historique (flèches haut/bas)
    # ------------------------------------------------------------------
    def _rappeler_historique(self, sens):
        if not self._historique:
            return None
        if self._index_historique is None:
            self._index_historique = len(self._historique)
        if sens == "up":
            self._index_historique = max(0, self._index_historique - 1)
        else:
            self._index_historique = min(len(self._historique), self._index_historique + 1)
        if self._index_historique == len(self._historique):
            return ""
        return self._historique[self._index_historique]

    # ------------------------------------------------------------------
    # Exécution
    # ------------------------------------------------------------------
    def executer(self, commande):
        commande = (commande or "").strip()
        if not commande or self._occupe:
            return
        self._historique.append(commande)
        self._index_historique = None
        self.entree.text = ""
        self._afficher("{} $ {}".format(self._prompt_chemin(), commande))

        if commande in ("clear", "cls"):
            self.effacer()
            return

        if commande == "cd" or commande.startswith("cd "):
            self._changer_dossier(commande[2:].strip())
            return

        self._lancer(commande)

    def _changer_dossier(self, chemin_txt):
        cible = os.path.expanduser(os.path.expandvars(chemin_txt or str(Path.home())))
        nouveau = Path(cible) if os.path.isabs(cible) else (self.cwd / cible)
        try:
            nouveau = nouveau.resolve()
            if nouveau.is_dir():
                self.cwd = nouveau
                self._maj_prompt()
            else:
                self._afficher("cd : dossier introuvable : {}".format(chemin_txt))
        except Exception as error:
            self._afficher("cd : {}".format(error))

    def _lancer(self, commande):
        self._occupe = True
        self.btn_executer.disabled = True
        self.btn_stop.disabled = False
        self.btn_stop.opacity = 1
        self.temoin_occupe.text = "EN COURS…"
        threading.Thread(target=self._executer_thread, args=(commande,),
                         daemon=True).start()

    def _executer_thread(self, commande):
        try:
            proc = subprocess.Popen(
                commande, shell=True, cwd=str(self.cwd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except Exception as error:
            Clock.schedule_once(
                lambda *_a: self._afficher("Erreur au lancement : {}".format(error)), 0)
            Clock.schedule_once(lambda *_a: self._fin_execution(), 0)
            return

        self._proc = proc
        try:
            for ligne in proc.stdout:
                ligne = ligne.rstrip("\n")
                Clock.schedule_once(lambda *_a, l=ligne: self._afficher(l), 0)
            proc.wait()
            code = proc.returncode
        except Exception as error:
            code = None
            Clock.schedule_once(
                lambda *_a: self._afficher("Erreur : {}".format(error)), 0)
        finally:
            self._proc = None
            Clock.schedule_once(lambda *_a: self._fin_execution(code), 0)

    def _fin_execution(self, code=None):
        self._occupe = False
        self.btn_executer.disabled = False
        self.btn_stop.disabled = True
        self.btn_stop.opacity = 0.4
        self.temoin_occupe.text = ""
        if code not in (None, 0):
            self._afficher("[terminé — code {}]".format(code))

    def arreter(self):
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception as error:
                print("[terminal] arret impossible :", error)
            self._afficher("[interrompu]")

    def on_leave(self, *_args):
        """En quittant l'app, on n'interrompt pas un traitement en cours
        (utile pour un long `apt upgrade` lancé puis consulté plus tard)."""
        return None


NovaApp = TerminalApp
