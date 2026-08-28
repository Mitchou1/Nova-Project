#!/usr/bin/env python3
"""App Fichiers NOVA.

Explore les dossiers de l'appareil : photos prises par la camera, fichiers
recus par Bluetooth, enregistrements... Permet de creer, renommer et
supprimer des dossiers, et de supprimer des fichiers.

Tout se passe dans le dossier `data/` de NOVA : on ne peut pas remonter
au-dessus, pour ne pas toucher au systeme par accident.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from apps.base_app import BaseApp
from nova import fonts
from nova.ui.theme import theme_manager
from nova.ui.widgets import GlassCard, NeonButton


def _racine():
    """Dossier racine accessible : les donnees de NOVA."""
    try:
        from nova.paths import DATA_DIR
        base = Path(DATA_DIR)
    except Exception:
        base = Path.home() / "nova_data"
    base.mkdir(parents=True, exist_ok=True)
    # Dossiers de base, crees s'ils n'existent pas
    for nom in ("photos", "bluetooth", "documents", "enregistrements"):
        (base / nom).mkdir(exist_ok=True)
    return base


def _taille_lisible(octets):
    """Convertit une taille en octets vers une forme lisible."""
    for unite in ("o", "Ko", "Mo", "Go"):
        if octets < 1024 or unite == "Go":
            return "{:.0f} {}".format(octets, unite)
        octets /= 1024.0
    return "{:.0f} Go".format(octets)



# Extensions reconnues, par famille
_IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
_TEXTES = {".txt", ".md", ".json", ".log", ".csv", ".py", ".sh", ".ini"}
_AUDIOS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
_VIDEOS = {".mp4", ".avi", ".mkv", ".mov"}


def _icone_fichier(chemin):
    """Choisit l'icone selon le type de fichier."""
    ext = chemin.suffix.lower()
    if ext in _IMAGES:
        return "image"
    if ext in _TEXTES:
        return "description"
    if ext in _AUDIOS:
        return "audiotrack"
    if ext in _VIDEOS:
        return "movie"
    return "insert_drive_file"


def _est_image(chemin):
    return chemin.suffix.lower() in _IMAGES


def _est_texte(chemin):
    return chemin.suffix.lower() in _TEXTES


class EntryRow(GlassCard):
    """Une ligne : dossier ou fichier."""

    def __init__(self, chemin, est_dossier, on_open=None, on_menu=None, **kwargs):
        super().__init__(size_hint=(1, None), height=dp(52),
                         corner_radius=dp(2), **kwargs)
        self.chemin = chemin
        self.est_dossier = est_dossier
        self.on_open = on_open
        self.on_menu = on_menu

        couleur = ("primary" if est_dossier else "text_secondary")
        icone = "folder" if est_dossier else _icone_fichier(chemin)

        # Icone
        self.add_widget(Label(
            text=fonts.icon_safe(icone), font_name=fonts.FONT_ICON,
            font_size=dp(20), color=theme_manager.get_color(couleur),
            pos_hint={"x": 0.02, "center_y": 0.5}, size_hint=(0.08, 0.7),
        ))

        # Nom
        self.add_widget(Label(
            text=chemin.name, font_name=fonts.FONT_DISPLAY, font_size=dp(13),
            color=theme_manager.get_color("text"),
            pos_hint={"x": 0.12, "center_y": 0.62}, size_hint=(0.62, 0.36),
            halign="left", valign="middle", shorten=True,
            shorten_from="right", text_size=(dp(300), None),
        ))

        # Details : nombre d'elements ou taille + date
        try:
            if est_dossier:
                nb = len(list(chemin.iterdir()))
                detail = "{} ÉLÉMENT{}".format(nb, "S" if nb > 1 else "")
            else:
                detail = _taille_lisible(chemin.stat().st_size)
            horodatage = datetime.fromtimestamp(chemin.stat().st_mtime)
            detail += "  ·  " + horodatage.strftime("%d/%m %H:%M")
        except Exception:
            detail = "—"

        self.add_widget(Label(
            text=detail, font_name=fonts.FONT_MONO, font_size=dp(9),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={"x": 0.12, "center_y": 0.28}, size_hint=(0.62, 0.3),
            halign="left", valign="middle", text_size=(dp(300), None),
        ))

        # Bouton menu (renommer / supprimer)
        menu = NeonButton(icon="more_vert", size_hint=(None, None),
                          size=(dp(34), dp(34)),
                          pos_hint={"right": 0.975, "center_y": 0.5},
                          corner_radius=dp(2))
        menu.bind(on_press=lambda *_a: self.on_menu and self.on_menu(self))
        self.add_widget(menu)

    def on_touch_down(self, touch):
        """Un appui ouvre le dossier, ou previsualise le fichier."""
        if self.collide_point(*touch.pos):
            # Laisser le bouton menu recevoir son propre appui
            for enfant in self.children:
                if hasattr(enfant, "icon") and enfant.collide_point(*touch.pos):
                    return super().on_touch_down(touch)
            if self.on_open:
                self.on_open(self.chemin)
                return True
        return super().on_touch_down(touch)


class FilesApp(BaseApp):
    """Explorateur de fichiers."""

    app_name = "Fichiers"
    app_icon = "folder"
    app_id = "files"

    def __init__(self, **kwargs):
        self.dossier_courant = _racine()
        self._presse_papier = None      # (chemin, "copier"|"couper")
        super().__init__(**kwargs)

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ─── Chemin actuel + bouton remonter ─────────────────────────
        barre = BoxLayout(size_hint=(0.95, None), height=dp(40),
                          pos_hint={"center_x": 0.5, "top": 0.97},
                          spacing=dp(8))

        self.btn_haut = NeonButton(icon="arrow_upward", size_hint=(None, 1),
                                   width=dp(48), corner_radius=dp(2))
        self.btn_haut.bind(on_press=lambda *_a: self.remonter())
        barre.add_widget(self.btn_haut)

        self.chemin_label = Label(
            text="/", font_name=fonts.FONT_MONO, font_size=dp(11),
            color=theme_manager.get_color("primary"),
            size_hint=(1, 1), halign="left", valign="middle",
        )
        self.chemin_label.bind(
            size=lambda w, s: setattr(w, "text_size", (s[0], s[1])))
        barre.add_widget(self.chemin_label)

        btn_nouveau = NeonButton(icon="create_new_folder", size_hint=(None, 1),
                                 width=dp(50), corner_radius=dp(2))
        btn_nouveau.bind(on_press=lambda *_a: self._demander_nom())
        barre.add_widget(btn_nouveau)

        btn_note = NeonButton(icon="note_add", size_hint=(None, 1),
                              width=dp(50), corner_radius=dp(2))
        btn_note.bind(on_press=lambda *_a: self._creer_note())
        barre.add_widget(btn_note)

        btn_import = NeonButton(icon="download", size_hint=(None, 1),
                                width=dp(50), corner_radius=dp(2))
        btn_import.bind(on_press=lambda *_a: self._importer())
        barre.add_widget(btn_import)

        # Bouton coller : visible seulement quand le presse-papier est plein
        self.btn_coller = NeonButton(icon="content_paste", size_hint=(None, 1),
                                     width=dp(50), corner_radius=dp(2))
        self.btn_coller.bind(on_press=lambda *_a: self.coller())
        self.btn_coller.opacity = 0
        self.btn_coller.disabled = True
        barre.add_widget(self.btn_coller)

        main.add_widget(barre)

        # ─── Liste ───────────────────────────────────────────────────
        self.scroll = ScrollView(size_hint=(0.95, 0.76),
                                 pos_hint={"center_x": 0.5, "top": 0.87})
        self.liste = BoxLayout(orientation="vertical", spacing=dp(6),
                               size_hint_y=None, padding=[0, dp(4)])
        self.liste.bind(minimum_height=self.liste.setter("height"))
        self.scroll.add_widget(self.liste)
        main.add_widget(self.scroll)

        # ─── Bandeau d'information ───────────────────────────────────
        self.info = Label(
            text="", font_name=fonts.FONT_MONO, font_size=dp(9),
            color=theme_manager.get_color("text_secondary"),
            size_hint=(0.95, None), height=dp(18),
            pos_hint={"center_x": 0.5, "y": 0.02},
        )
        main.add_widget(self.info)

        self.rafraichir()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def rafraichir(self):
        """Relit le dossier courant et reconstruit la liste."""
        self.liste.clear_widgets()
        racine = _racine()

        # Chemin affiche, relatif a la racine
        try:
            relatif = self.dossier_courant.relative_to(racine)
            self.chemin_label.text = "/" + str(relatif) if str(relatif) != "." else "/"
        except ValueError:
            self.dossier_courant = racine
            self.chemin_label.text = "/"

        self.btn_haut.disabled = (self.dossier_courant == racine)

        try:
            entrees = sorted(self.dossier_courant.iterdir(),
                             key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception as error:
            print("[fichiers] lecture impossible :", error)
            entrees = []

        if not entrees:
            self.liste.add_widget(Label(
                text="DOSSIER VIDE", font_name=fonts.FONT_MONO, font_size=dp(10),
                color=theme_manager.get_color("text_secondary"),
                size_hint_y=None, height=dp(40)))
        else:
            for chemin in entrees:
                ligne = EntryRow(chemin, chemin.is_dir(),
                                 on_open=self.ouvrir, on_menu=self._menu)
                self.liste.add_widget(ligne)

        dossiers = sum(1 for e in entrees if e.is_dir())
        fichiers = len(entrees) - dossiers
        self.info.text = "{} DOSSIER{}  ·  {} FICHIER{}".format(
            dossiers, "S" if dossiers > 1 else "",
            fichiers, "S" if fichiers > 1 else "")

    def ouvrir(self, chemin):
        """Entre dans un dossier, ou previsualise un fichier."""
        if chemin.is_dir():
            self.dossier_courant = chemin
            self.rafraichir()
        else:
            self.previsualiser(chemin)

    # ------------------------------------------------------------------
    # Lecture des fichiers
    # ------------------------------------------------------------------
    def previsualiser(self, chemin):
        """Affiche une image en grand, ou le contenu d'un fichier texte."""
        from kivy.uix.image import Image as KivyImage

        boite = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        popup = Popup(title=chemin.name, content=boite, size_hint=(0.92, 0.88),
                      separator_height=dp(1))

        if _est_image(chemin):
            try:
                if chemin.stat().st_size == 0:
                    boite.add_widget(Label(
                        text="IMAGE VIDE\n(photo simulee, aucune camera connectee)",
                        font_name=fonts.FONT_MONO, font_size=dp(11),
                        color=theme_manager.get_color("text_secondary"),
                        halign="center"))
                else:
                    boite.add_widget(KivyImage(source=str(chemin),
                                               allow_stretch=True,
                                               keep_ratio=True))
            except Exception as error:
                print("[fichiers] image illisible :", error)
                boite.add_widget(Label(text="IMAGE ILLISIBLE",
                                       color=theme_manager.get_color("error")))

        elif _est_texte(chemin):
            defilement = ScrollView()
            try:
                contenu = chemin.read_text(encoding="utf-8", errors="replace")
            except Exception as error:
                contenu = "Lecture impossible : {}".format(error)
            if len(contenu) > 20000:
                contenu = contenu[:20000] + "\n\n[... fichier tronque ...]"
            texte = Label(text=contenu or "(fichier vide)",
                          font_name=fonts.FONT_MONO, font_size=dp(11),
                          color=theme_manager.get_color("text"),
                          size_hint_y=None, halign="left", valign="top")
            texte.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                       texture_size=lambda w, v: setattr(w, "height", v[1]))
            defilement.add_widget(texte)
            boite.add_widget(defilement)

        else:
            taille = _taille_lisible(chemin.stat().st_size)
            boite.add_widget(Label(
                text="APERÇU INDISPONIBLE\n\n{}\n{}".format(chemin.suffix.upper()
                                                              or "SANS EXTENSION", taille),
                font_name=fonts.FONT_MONO, font_size=dp(11),
                color=theme_manager.get_color("text_secondary"), halign="center"))

        fermer = NeonButton(text="FERMER", size_hint_y=None, height=dp(44),
                            corner_radius=dp(2))
        fermer.bind(on_press=lambda *_a: popup.dismiss())
        boite.add_widget(fermer)
        popup.open()

    def remonter(self):
        """Remonte d'un niveau, sans depasser la racine."""
        racine = _racine()
        if self.dossier_courant != racine:
            self.dossier_courant = self.dossier_courant.parent
            self.rafraichir()

    # ------------------------------------------------------------------
    # Creer / renommer / supprimer
    # ------------------------------------------------------------------
    def _saisie(self, titre, valeur_initiale, on_valider):
        """Petite fenetre de saisie de texte."""
        boite = BoxLayout(orientation="vertical", spacing=dp(10),
                          padding=dp(14))
        champ = TextInput(text=valeur_initiale, multiline=False,
                          font_name=fonts.FONT_MONO, font_size=dp(13),
                          size_hint_y=None, height=dp(42),
                          background_color=theme_manager.get_with_alpha("surface", 0.9),
                          foreground_color=theme_manager.get_color("text"),
                          cursor_color=theme_manager.get_color("primary"))
        boite.add_widget(champ)

        rangee = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        popup = Popup(title=titre, content=boite, size_hint=(0.8, 0.45),
                      separator_height=dp(1))

        annuler = NeonButton(text="ANNULER", corner_radius=dp(2))
        annuler.bind(on_press=lambda *_a: popup.dismiss())
        valider = NeonButton(text="VALIDER", corner_radius=dp(2))

        def _ok(*_a):
            nom = champ.text.strip()
            popup.dismiss()
            if nom:
                on_valider(nom)
        valider.bind(on_press=_ok)
        champ.bind(on_text_validate=_ok)

        rangee.add_widget(annuler)
        rangee.add_widget(valider)
        boite.add_widget(rangee)
        popup.open()

    def _demander_nom(self):
        """Demande le nom du nouveau dossier."""
        self._saisie("NOUVEAU DOSSIER", "", self.creer_dossier)

    def creer_dossier(self, nom):
        """Cree un dossier dans le dossier courant."""
        nom = "".join(c for c in nom if c not in '/\\:*?"<>|').strip()
        if not nom:
            self._message("NOM INVALIDE")
            return
        cible = self.dossier_courant / nom
        try:
            if cible.exists():
                self._message("CE DOSSIER EXISTE DÉJÀ")
                return
            cible.mkdir()
            self.rafraichir()
            self._message("DOSSIER CRÉÉ : {}".format(nom))
        except Exception as error:
            print("[fichiers] creation impossible :", error)
            self._message("CRÉATION IMPOSSIBLE")

    def _menu(self, ligne):
        """Menu d'une entree : renommer ou supprimer."""
        boite = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(14))
        boite.add_widget(Label(
            text=ligne.chemin.name, font_name=fonts.FONT_DISPLAY,
            font_size=dp(14), color=theme_manager.get_color("text")))

        popup = Popup(title="ACTIONS", content=boite, size_hint=(0.75, 0.5),
                      separator_height=dp(1))

        copier = NeonButton(text="COPIER", size_hint_y=None, height=dp(42),
                            corner_radius=dp(2))
        copier.bind(on_press=lambda *_a: (popup.dismiss(),
                                          self.presse_papier(ligne.chemin, "copier")))
        boite.add_widget(copier)

        couper = NeonButton(text="DÉPLACER", size_hint_y=None, height=dp(42),
                            corner_radius=dp(2))
        couper.bind(on_press=lambda *_a: (popup.dismiss(),
                                          self.presse_papier(ligne.chemin, "couper")))
        boite.add_widget(couper)

        renommer = NeonButton(text="RENOMMER", size_hint_y=None, height=dp(42),
                              corner_radius=dp(2))
        renommer.bind(on_press=lambda *_a: (
            popup.dismiss(),
            self._saisie("RENOMMER", ligne.chemin.name,
                         lambda n: self.renommer(ligne.chemin, n))))
        boite.add_widget(renommer)

        supprimer = NeonButton(text="SUPPRIMER", accent="error",
                               size_hint_y=None, height=dp(42),
                               corner_radius=dp(2))
        supprimer.bind(on_press=lambda *_a: (
            popup.dismiss(), self._confirmer_suppression(ligne.chemin)))
        boite.add_widget(supprimer)

        fermer = NeonButton(text="FERMER", size_hint_y=None, height=dp(38),
                            corner_radius=dp(2))
        fermer.bind(on_press=lambda *_a: popup.dismiss())
        boite.add_widget(fermer)
        popup.size_hint = (0.75, 0.72)
        popup.open()

    def renommer(self, chemin, nouveau_nom):
        """Renomme un dossier ou un fichier."""
        nouveau_nom = "".join(c for c in nouveau_nom
                              if c not in '/\\:*?"<>|').strip()
        if not nouveau_nom:
            self._message("NOM INVALIDE")
            return
        cible = chemin.parent / nouveau_nom
        try:
            if cible.exists():
                self._message("CE NOM EXISTE DÉJÀ")
                return
            chemin.rename(cible)
            self.rafraichir()
            self._message("RENOMMÉ : {}".format(nouveau_nom))
        except Exception as error:
            print("[fichiers] renommage impossible :", error)
            self._message("RENOMMAGE IMPOSSIBLE")

    def _confirmer_suppression(self, chemin):
        """Demande confirmation avant de supprimer (action irreversible)."""
        est_dossier = chemin.is_dir()
        contenu = ""
        if est_dossier:
            try:
                nb = len(list(chemin.iterdir()))
                if nb:
                    contenu = "\net son contenu ({} élément{})".format(
                        nb, "s" if nb > 1 else "")
            except Exception:
                pass

        boite = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(14))
        boite.add_widget(Label(
            text="Supprimer « {} »{} ?".format(chemin.name, contenu),
            color=theme_manager.get_color("text"), halign="center"))

        popup = Popup(title="CONFIRMER", content=boite, size_hint=(0.78, 0.42),
                      separator_height=dp(1))
        rangee = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))

        annuler = NeonButton(text="ANNULER", corner_radius=dp(2))
        annuler.bind(on_press=lambda *_a: popup.dismiss())
        confirmer = NeonButton(text="SUPPRIMER", accent="error",
                               corner_radius=dp(2))
        confirmer.bind(on_press=lambda *_a: (popup.dismiss(),
                                             self.supprimer(chemin)))
        rangee.add_widget(annuler)
        rangee.add_widget(confirmer)
        boite.add_widget(rangee)
        popup.open()

    def supprimer(self, chemin):
        """Supprime un fichier ou un dossier (avec son contenu)."""
        try:
            if chemin.is_dir():
                shutil.rmtree(chemin)
            else:
                chemin.unlink()
            self.rafraichir()
            self._message("SUPPRIMÉ : {}".format(chemin.name))
        except Exception as error:
            print("[fichiers] suppression impossible :", error)
            self._message("SUPPRESSION IMPOSSIBLE")


    # ------------------------------------------------------------------
    # Copier / deplacer (presse-papier)
    # ------------------------------------------------------------------
    def presse_papier(self, chemin, operation):
        """Met un element en attente de collage."""
        self._presse_papier = (chemin, operation)
        self.btn_coller.opacity = 1
        self.btn_coller.disabled = False
        verbe = "COPIÉ" if operation == "copier" else "COUPÉ"
        self._message("{} : {} — ouvrez un dossier puis collez".format(
            verbe, chemin.name))

    def coller(self):
        """Colle l'element du presse-papier dans le dossier courant."""
        if not self._presse_papier:
            return
        source, operation = self._presse_papier
        if not source.exists():
            self._message("LA SOURCE N'EXISTE PLUS")
            self._vider_presse_papier()
            return

        cible = self.dossier_courant / source.name
        # Ne pas coller un dossier dans lui-meme
        try:
            if source.is_dir() and self.dossier_courant.is_relative_to(source):
                self._message("IMPOSSIBLE : DOSSIER DANS LUI-MÊME")
                return
        except AttributeError:      # Python < 3.9
            if source.is_dir() and str(self.dossier_courant).startswith(str(source)):
                self._message("IMPOSSIBLE : DOSSIER DANS LUI-MÊME")
                return

        # Nom unique si un element du meme nom existe deja
        if cible.exists():
            base, ext = source.stem, source.suffix
            n = 2
            while cible.exists():
                cible = self.dossier_courant / "{} ({}){}".format(base, n, ext)
                n += 1

        try:
            if operation == "copier":
                if source.is_dir():
                    shutil.copytree(source, cible)
                else:
                    shutil.copy2(source, cible)
                self._message("COPIÉ : {}".format(cible.name))
            else:
                shutil.move(str(source), str(cible))
                self._message("DÉPLACÉ : {}".format(cible.name))
                self._vider_presse_papier()
            self.rafraichir()
        except Exception as error:
            print("[fichiers] collage impossible :", error)
            self._message("COLLAGE IMPOSSIBLE")

    def _vider_presse_papier(self):
        self._presse_papier = None
        self.btn_coller.opacity = 0
        self.btn_coller.disabled = True

    # ------------------------------------------------------------------
    # Creer une note texte
    # ------------------------------------------------------------------
    def _creer_note(self):
        """Demande un nom, puis ouvre l'editeur de note."""
        defaut = "note_{}.txt".format(datetime.now().strftime("%Y%m%d_%H%M"))
        self._saisie("NOUVELLE NOTE", defaut, self._editer_note)

    def _editer_note(self, nom):
        """Editeur de texte simple, enregistre dans le dossier courant."""
        if not nom.lower().endswith((".txt", ".md")):
            nom += ".txt"
        nom = "".join(c for c in nom if c not in '/\\:*?"<>|').strip()
        chemin = self.dossier_courant / nom

        contenu_initial = ""
        if chemin.exists():
            try:
                contenu_initial = chemin.read_text(encoding="utf-8",
                                                   errors="replace")
            except Exception:
                pass

        boite = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        champ = TextInput(text=contenu_initial, multiline=True,
                          font_name=fonts.FONT_MONO, font_size=dp(12),
                          background_color=theme_manager.get_with_alpha("surface", 0.9),
                          foreground_color=theme_manager.get_color("text"),
                          cursor_color=theme_manager.get_color("primary"))
        boite.add_widget(champ)

        popup = Popup(title=nom, content=boite, size_hint=(0.92, 0.85),
                      separator_height=dp(1))
        rangee = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))

        annuler = NeonButton(text="ANNULER", corner_radius=dp(2))
        annuler.bind(on_press=lambda *_a: popup.dismiss())
        enregistrer = NeonButton(text="ENREGISTRER", corner_radius=dp(2))

        def _sauver(*_a):
            popup.dismiss()
            try:
                chemin.write_text(champ.text, encoding="utf-8")
                self.rafraichir()
                self._message("NOTE ENREGISTRÉE : {}".format(nom))
            except Exception as error:
                print("[fichiers] ecriture impossible :", error)
                self._message("ENREGISTREMENT IMPOSSIBLE")
        enregistrer.bind(on_press=_sauver)

        rangee.add_widget(annuler)
        rangee.add_widget(enregistrer)
        boite.add_widget(rangee)
        popup.open()

    # ------------------------------------------------------------------
    # Importer depuis l'exterieur (cle USB, dossier du systeme)
    # ------------------------------------------------------------------
    def _sources_externes(self):
        """Liste les emplacements ou chercher des fichiers a importer."""
        sources = []
        # Cles USB et disques montes
        for base in ("/media", "/mnt", "/run/media"):
            b = Path(base)
            if b.exists():
                try:
                    for element in b.iterdir():
                        if element.is_dir():
                            sources.append(element)
                        # /media/<utilisateur>/<cle>
                        if element.is_dir():
                            for sous in element.iterdir():
                                if sous.is_dir():
                                    sources.append(sous)
                except Exception:
                    pass
        # Dossiers personnels classiques
        for nom in ("Téléchargements", "Downloads", "Images", "Pictures",
                    "Documents", "Bureau", "Desktop"):
            d = Path.home() / nom
            if d.is_dir():
                sources.append(d)
        # Sans doublons, ordre conserve
        vues, uniques = set(), []
        for s in sources:
            if str(s) not in vues:
                vues.add(str(s))
                uniques.append(s)
        return uniques

    def _importer(self):
        """Propose des emplacements externes, puis les fichiers a importer."""
        sources = self._sources_externes()
        boite = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(12))
        popup = Popup(title="IMPORTER DEPUIS", content=boite,
                      size_hint=(0.85, 0.8), separator_height=dp(1))

        if not sources:
            boite.add_widget(Label(
                text="AUCUNE SOURCE TROUVÉE\n\nBranchez une clé USB\n"
                     "ou placez des fichiers dans Téléchargements",
                font_name=fonts.FONT_MONO, font_size=dp(10),
                color=theme_manager.get_color("text_secondary"),
                halign="center"))
        else:
            defilement = ScrollView()
            liste = BoxLayout(orientation="vertical", spacing=dp(5),
                              size_hint_y=None)
            liste.bind(minimum_height=liste.setter("height"))
            for source in sources[:14]:
                bouton = NeonButton(text=str(source), size_hint_y=None,
                                    height=dp(40), corner_radius=dp(2))
                bouton.bind(on_press=lambda _b, s=source: (
                    popup.dismiss(), self._choisir_fichier(s)))
                liste.add_widget(bouton)
            defilement.add_widget(liste)
            boite.add_widget(defilement)

        fermer = NeonButton(text="FERMER", size_hint_y=None, height=dp(42),
                            corner_radius=dp(2))
        fermer.bind(on_press=lambda *_a: popup.dismiss())
        boite.add_widget(fermer)
        popup.open()

    def _choisir_fichier(self, source):
        """Liste les fichiers d'une source externe et en importe un."""
        try:
            fichiers = sorted([f for f in source.iterdir() if f.is_file()],
                              key=lambda p: p.name.lower())[:60]
        except Exception as error:
            print("[fichiers] lecture source impossible :", error)
            self._message("SOURCE ILLISIBLE")
            return

        boite = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(12))
        popup = Popup(title=str(source), content=boite, size_hint=(0.9, 0.85),
                      separator_height=dp(1))

        if not fichiers:
            boite.add_widget(Label(text="AUCUN FICHIER ICI",
                                   font_name=fonts.FONT_MONO, font_size=dp(10),
                                   color=theme_manager.get_color("text_secondary")))
        else:
            defilement = ScrollView()
            liste = BoxLayout(orientation="vertical", spacing=dp(4),
                              size_hint_y=None)
            liste.bind(minimum_height=liste.setter("height"))
            for fichier in fichiers:
                etiquette = "{}   ({})".format(
                    fichier.name, _taille_lisible(fichier.stat().st_size))
                bouton = NeonButton(text=etiquette, size_hint_y=None,
                                    height=dp(38), corner_radius=dp(2))
                bouton.bind(on_press=lambda _b, f=fichier: (
                    popup.dismiss(), self.importer_fichier(f)))
                liste.add_widget(bouton)
            defilement.add_widget(liste)
            boite.add_widget(defilement)

        fermer = NeonButton(text="FERMER", size_hint_y=None, height=dp(42),
                            corner_radius=dp(2))
        fermer.bind(on_press=lambda *_a: popup.dismiss())
        boite.add_widget(fermer)
        popup.open()

    def importer_fichier(self, source):
        """Copie un fichier externe dans le dossier courant."""
        cible = self.dossier_courant / source.name
        if cible.exists():
            base, ext = source.stem, source.suffix
            n = 2
            while cible.exists():
                cible = self.dossier_courant / "{} ({}){}".format(base, n, ext)
                n += 1
        try:
            shutil.copy2(source, cible)
            self.rafraichir()
            self._message("IMPORTÉ : {}".format(cible.name))
        except Exception as error:
            print("[fichiers] import impossible :", error)
            self._message("IMPORT IMPOSSIBLE")

    def _message(self, texte, duree=2.5):
        """Affiche un message temporaire dans le bandeau du bas."""
        self.info.text = texte
        Clock.schedule_once(lambda *_a: self.rafraichir(), duree)

    def on_enter(self, *_args):
        """Relit le dossier a chaque ouverture de l'app."""
        try:
            self.rafraichir()
        except Exception as error:
            print("[fichiers] rafraichissement :", error)


NovaApp = FilesApp
