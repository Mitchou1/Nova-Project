#!/usr/bin/env python3
"""App Caméra NOVA (cahier des charges, Phase 8).

Fonctions : apercu, prise de photo, galerie des cliches.
Sur le Raspberry Pi : Pi Camera via libcamera-still. Sur PC : vraie capture
webcam (ffmpeg + v4l2) si une camera est branchee ; sinon repli honnete
(fichier marqueur, etat affiche clairement) pour que la chaine reste testable.
"""

import os
from datetime import datetime

from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from apps.base_app import BaseApp
from nova import fonts
from nova.ui.theme import theme_manager
from nova.ui.widgets import GlassCard, NeonButton


def _sur_pi():
    try:
        from nova.utils.platform_utils import is_raspberry_pi
        return is_raspberry_pi()
    except Exception:
        return False


def _peripherique_webcam():
    """Renvoie le premier /dev/videoN trouve, ou None."""
    for candidat in ("/dev/video0", "/dev/video1", "/dev/video2"):
        if os.path.exists(candidat):
            return candidat
    return None


def _webcam_disponible():
    import shutil
    return shutil.which("ffmpeg") is not None and _peripherique_webcam() is not None


def _dossier_photos():
    """Dossier ou sont enregistrees les photos."""
    try:
        from nova.paths import DATA_DIR
        dossier = DATA_DIR / "photos"
    except Exception:
        from pathlib import Path
        dossier = Path.home() / "nova_photos"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


class Viewfinder(Widget):
    """Zone d'apercu : image de la camera, ou mire en simulation."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas:
            self._fond_color = Color(0.06, 0.07, 0.08, 1)
            self._fond = Rectangle()
            # Reperes de cadrage facon viseur (charte NOVA)
            self._reperes_color = Color(*theme_manager.get_with_alpha("primary", 0.55))
            self._reperes = [Line(width=dp(1.4)) for _ in range(4)]
            # Croix centrale
            self._croix_color = Color(*theme_manager.get_with_alpha("primary", 0.3))
            self._croix = [Line(width=dp(1)) for _ in range(2)]
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *_a):
        x, y, w, h = self.x, self.y, self.width, self.height
        self._fond.pos = (x, y)
        self._fond.size = (w, h)

        # Quatre equerres aux coins (viseur)
        c = min(dp(26), w * 0.16, h * 0.22)
        m = dp(8)
        self._reperes[0].points = [x + m, y + h - m - c, x + m, y + h - m,
                                   x + m + c, y + h - m]
        self._reperes[1].points = [x + w - m - c, y + h - m, x + w - m, y + h - m,
                                   x + w - m, y + h - m - c]
        self._reperes[2].points = [x + m, y + m + c, x + m, y + m, x + m + c, y + m]
        self._reperes[3].points = [x + w - m - c, y + m, x + w - m, y + m,
                                   x + w - m, y + m + c]

        # Croix de visee au centre
        cx, cy = x + w / 2, y + h / 2
        t = dp(10)
        self._croix[0].points = [cx - t, cy, cx + t, cy]
        self._croix[1].points = [cx, cy - t, cx, cy + t]

    def flash(self):
        """Eclair blanc bref au moment de la prise de vue."""
        from kivy.animation import Animation

        with self.canvas:
            couleur = Color(1, 1, 1, 0.85)
            rect = Rectangle(pos=self.pos, size=self.size)

        def effacer(*_a):
            self.canvas.remove(rect)
            self.canvas.remove(couleur)

        anim = Animation(a=0, duration=0.35, t="out_quad")
        anim.bind(on_complete=effacer)
        anim.start(couleur)


class CameraApp(BaseApp):
    """Application Camera."""

    app_name = "Caméra"
    app_icon = "photo_camera"
    app_id = "camera"

    def __init__(self, **kwargs):
        self.photos = []
        self._camera = None
        super().__init__(**kwargs)

    def build_ui(self):
        # Construit d'abord l'en-tete commun (bouton RETOUR + titre)
        super().build_ui()
        main = self.children[0]

        # ─── Bandeau d'etat ──────────────────────────────────────────
        etat = GlassCard(size_hint=(0.95, None), height=dp(26),
                         pos_hint={"center_x": 0.5, "top": 0.97},
                         corner_radius=dp(2))
        self.etat_label = Label(
            text=self._texte_etat_repos(),
            font_name=fonts.FONT_MONO, font_size=dp(9),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        etat.add_widget(self.etat_label)
        main.add_widget(etat)

        # ─── Viseur ──────────────────────────────────────────────────
        self.viseur = Viewfinder(size_hint=(0.95, 0.52),
                                 pos_hint={"center_x": 0.5, "top": 0.92})
        main.add_widget(self.viseur)

        # ─── Compteur de photos ──────────────────────────────────────
        self.compteur = Label(
            text="0 PHOTO", font_name=fonts.FONT_MONO, font_size=dp(9),
            color=theme_manager.get_color("text_secondary"),
            size_hint=(0.95, None), height=dp(16),
            pos_hint={"center_x": 0.5, "top": 0.38},
        )
        main.add_widget(self.compteur)

        # ─── Commandes ───────────────────────────────────────────────
        barre = BoxLayout(size_hint=(0.95, None), height=dp(46),
                          pos_hint={"center_x": 0.5, "y": 0.14},
                          spacing=dp(10))

        self.btn_photo = NeonButton(icon="photo_camera", text="PHOTO",
                                    corner_radius=dp(2))
        self.btn_photo.bind(on_press=lambda *_a: self.prendre_photo())
        barre.add_widget(self.btn_photo)

        btn_galerie = NeonButton(icon="collections", text="GALERIE",
                                 corner_radius=dp(2))
        btn_galerie.bind(on_press=lambda *_a: self._afficher_galerie())
        barre.add_widget(btn_galerie)

        btn_dossier = NeonButton(icon="folder", text="DOSSIER",
                                 corner_radius=dp(2))
        btn_dossier.bind(on_press=lambda *_a: self._montrer_dossier())
        barre.add_widget(btn_dossier)

        main.add_widget(barre)

        # ─── Zone galerie (liste des cliches) ────────────────────────
        self.galerie_scroll = ScrollView(size_hint=(0.95, 0.10),
                                         pos_hint={"center_x": 0.5, "y": 0.03})
        self.galerie_box = BoxLayout(orientation="vertical", spacing=dp(3),
                                     size_hint_y=None)
        self.galerie_box.bind(
            minimum_height=self.galerie_box.setter("height"))
        self.galerie_scroll.add_widget(self.galerie_box)
        main.add_widget(self.galerie_scroll)

        self._charger_photos()

    # ------------------------------------------------------------------
    def _charger_photos(self):
        """Recense les photos deja enregistrees."""
        try:
            dossier = _dossier_photos()
            self.photos = sorted(
                [f for f in os.listdir(dossier)
                 if f.lower().endswith((".jpg", ".png"))],
                reverse=True)
        except Exception as error:
            print("[camera] lecture du dossier impossible :", error)
            self.photos = []
        self._maj_compteur()

    def _maj_compteur(self):
        nombre = len(self.photos)
        self.compteur.text = "{} PHOTO{}".format(nombre, "S" if nombre > 1 else "")

    def prendre_photo(self):
        """Prend une photo (Pi Camera) ou enregistre un cliche de test."""
        self.viseur.flash()
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        nom = "nova_{}.jpg".format(horodatage)
        chemin = _dossier_photos() / nom

        if _sur_pi():
            try:
                # Emplacement pour la vraie Pi Camera :
                #   from picamera2 import Picamera2
                #   cam = Picamera2(); cam.start(); cam.capture_file(str(chemin))
                import subprocess
                subprocess.run(["libcamera-still", "-o", str(chemin), "-n",
                                "-t", "300"],
                               capture_output=True, timeout=8)
            except Exception as error:
                print("[camera] capture impossible :", error)
                self.etat_label.text = "ERREUR DE CAPTURE"
                return None
        else:
            # PC : vraie capture webcam via ffmpeg (v4l2) si une camera est
            # branchee — pas de fichier vide silencieux quand on peut faire
            # mieux. Repli honnete (fichier marqueur + etat explicite) sinon.
            if self._capturer_webcam(chemin):
                pass
            else:
                try:
                    chemin.write_bytes(b"")
                except Exception as error:
                    print("[camera] ecriture impossible :", error)
                    return None
                self.etat_label.text = "AUCUNE WEBCAM — FICHIER TEST (VIDE)"
                self.photos.insert(0, nom)
                self._maj_compteur()
                Clock.schedule_once(lambda *_a: self._reset_etat(), 2.5)
                print("[camera] photo (marqueur, aucune webcam) :", chemin)
                return str(chemin)

        self.photos.insert(0, nom)
        self._maj_compteur()
        self.etat_label.text = "PHOTO ENREGISTRÉE — {}".format(nom)
        Clock.schedule_once(lambda *_a: self._reset_etat(), 2.5)
        print("[camera] photo :", chemin)
        return str(chemin)

    def _capturer_webcam(self, chemin):
        """Capture une vraie image via ffmpeg + v4l2 (pas de dependance
        Python lourde type OpenCV pour un simple instantane de test)."""
        peripherique = _peripherique_webcam()
        if peripherique is None:
            return False
        import shutil
        import subprocess
        if shutil.which("ffmpeg") is None:
            return False
        try:
            resultat = subprocess.run(
                ["ffmpeg", "-y", "-f", "v4l2", "-i", peripherique,
                 "-frames:v", "1", "-update", "1", str(chemin)],
                capture_output=True, timeout=6)
            return (resultat.returncode == 0 and chemin.exists()
                    and chemin.stat().st_size > 0)
        except Exception as error:
            print("[camera] capture webcam impossible :", error)
            return False

    def _texte_etat_repos(self):
        if _sur_pi():
            return "CAMÉRA PRÊTE"
        if _webcam_disponible():
            return "WEBCAM PRÊTE ({})".format(_peripherique_webcam())
        return "AUCUNE WEBCAM DÉTECTÉE"

    def _reset_etat(self):
        self.etat_label.text = self._texte_etat_repos()

    def _afficher_galerie(self):
        """Liste les photos dans la zone du bas."""
        self.galerie_box.clear_widgets()
        self._charger_photos()
        if not self.photos:
            self.galerie_box.add_widget(Label(
                text="AUCUNE PHOTO", font_name=fonts.FONT_MONO, font_size=dp(9),
                color=theme_manager.get_color("text_secondary"),
                size_hint_y=None, height=dp(20)))
            return
        for nom in self.photos[:12]:
            self.galerie_box.add_widget(Label(
                text=nom, font_name=fonts.FONT_MONO, font_size=dp(9),
                color=theme_manager.get_color("primary"),
                size_hint_y=None, height=dp(18)))

    def _montrer_dossier(self):
        self.etat_label.text = str(_dossier_photos())
        Clock.schedule_once(lambda *_a: self._reset_etat(), 4)


NovaApp = CameraApp
