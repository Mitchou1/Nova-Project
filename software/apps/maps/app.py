#!/usr/bin/env python3
"""
App Maps NOVA — Navigation GPS.
Vraie carte (tuiles locales Tunisie + routage Valhalla), position GPS simulee
sur PC (autour de Tunis) tant qu'aucun module NEO-6M n'est branche.
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.metrics import dp
import random

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager
from nova.ui.widgets import GlassCard, NeonButton


def _opaque_backdrop(widget, alpha=0.88):
    """Pose un fond opaque sombre derriere un widget.

    La carte MapTiler est claire : les panneaux "verre" translucides du
    theme y deviennent laiteux et illisibles. On dessine donc un aplat
    sombre derriere eux, qui suit leur position et leur taille.
    """
    from kivy.graphics import Color, Rectangle
    from nova.ui.theme import theme_manager as _tm

    base = _tm.get_color("background")
    with widget.canvas.before:
        col = Color(base[0], base[1], base[2], alpha)
        rect = Rectangle(pos=widget.pos, size=widget.size)

    def _follow(*_a):
        rect.pos = widget.pos
        rect.size = widget.size
    widget.bind(pos=_follow, size=_follow)
    _follow()
    return rect


class MapsApp(BaseApp):
    """Application Maps avec simulation."""

    app_name = "Maps"
    app_icon = "explore"
    app_id = "maps"

    def __init__(self, **kwargs):
        self.latitude = 36.8065
        self.longitude = 10.1815
        self.speed = 0.0
        self.altitude = 15.0
        self.mode = "normal"
        self._movement_clock = None
        super().__init__(**kwargs)
        # Gestionnaire du serveur de carte local (démarre/arrête avec l'app)
        self._map_ready = False
        self._services_listener = None
        self._online_tiles = False   # True si on a basculé sur les tuiles internet
        # Navigation
        self._current_route = None
        self._current_dest = None
        self._nav_active = False
        self._nav_step = 0
        self._start_btn = None
        self._nav_btn = None
        self._stop_nav_btn = None

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ─── VRAIE CARTE (rues réelles de Tunis) ──────────────────
        # La carte occupe le centre, SOUS l'en-tête (RETOUR + titre) et SOUS
        # la barre de recherche, pour ne pas les recouvrir.
        from nova.ui.map_engine import MapView
        from nova.paths import MAP_TILES_DIR
        self.map_widget = MapView(
            str(MAP_TILES_DIR),
            center_lat=self.latitude, center_lon=self.longitude,
            zoom=14, online=True,      # télécharge les vraies tuiles + cache local
            size_hint=(1, 0.52),
            pos_hint={'x': 0, 'top': 0.82}
        )
        main.add_widget(self.map_widget)

        # ─── BARRE DE RECHERCHE (destination) ─────────────────────
        # Placée SOUS l'en-tête (l'en-tête est tout en haut, ~top 0.9-1.0)
        # 44 px (cible tactile) et 6 px sous l'en-tête (RETOUR) : à « top
        # 0.88 » elle touchait l'en-tête.
        search_bar = BoxLayout(
            size_hint=(0.92, None), height=dp(44), spacing=dp(6),
            # sous le trait de l'en-tête (qui traversait la barre)
            pos_hint={'center_x': 0.5, 'top': 1 - (dp(14) + dp(44) + dp(10) + dp(1) + dp(4)) / 480.0}
        )
        self.search_input = TextInput(
            hint_text="Rechercher une destination...",
            multiline=False, size_hint=(1, 1),
            font_size=dp(14), padding=[dp(10), dp(10)],
            background_color=theme_manager.get_with_alpha("surface", 0.92),
            foreground_color=theme_manager.get_color("text"),
            cursor_color=theme_manager.get_color("primary"),
        )
        self.search_input.bind(on_text_validate=self._on_search)
        search_bar.add_widget(self.search_input)
        # La carte est claire : on pose un fond opaque sombre derriere la
        # barre, sinon le "verre" translucide devient laiteux et illisible.
        _opaque_backdrop(search_bar)

        go_btn = NeonButton(icon="search", size_hint=(None, 1),
                            width=dp(52), corner_radius=dp(2))
        go_btn.bind(on_press=lambda x: self._on_search(self.search_input))
        search_bar.add_widget(go_btn)
        main.add_widget(search_bar)

        # bandeau d'info navigation (distance/durée), caché au départ
        self.nav_info = Label(
            text="", font_size=dp(12), markup=True,
            color=theme_manager.get_color("primary"),
            size_hint=(0.92, None), height=dp(22),
            # juste SOUS la barre de recherche (top 0.88, 40 dp) : à 0.83 le
            # bandeau chevauchait le champ de saisie.
            pos_hint={'center_x': 0.5, 'top': 1 - (dp(14) + dp(44) + dp(15) + dp(44) + dp(4)) / 480.0},
            halign='center', valign='middle', opacity=0,
        )
        # Largeur fixe, hauteur qui suit le texte : les messages d'état
        # (détail des 3 services, cause d'une panne) font plusieurs lignes et
        # étaient tronqués à une seule. Fond opaque : lisible sur la carte.
        self.nav_info.bind(
            width=lambda w, v: setattr(w, "text_size", (v, None)),
            texture_size=lambda w, ts: setattr(w, "height", max(dp(22), ts[1] + dp(8))))
        _opaque_backdrop(self.nav_info)
        main.add_widget(self.nav_info)

        # ─── INFO PANEL ────────────────────────────────────────────
        info_card = GlassCard(
            size_hint=(0.95, None),
            height=dp(120),
            pos_hint={'center_x': 0.5, 'y': 0.12},
            corner_radius=dp(2)
        )

        # Coordonnées
        self.coord_label = Label(
            text="36.8065°N  10.1815°E",
            font_size=dp(16),
            bold=True,
            color=theme_manager.get_color("text"),
            pos_hint={'x': 0.05, 'top': 0.9},
            size_hint=(0.9, 0.25),
            halign='left'
        )
        info_card.add_widget(self.coord_label)

        # Vitesse + Altitude
        self.speed_label = Label(
            text="0.0 km/h",
            font_size=dp(24),
            bold=True,
            color=theme_manager.get_color("primary"),
            pos_hint={'x': 0.05, 'top': 0.6},
            size_hint=(0.4, 0.3),
            halign='left'
        )
        info_card.add_widget(self.speed_label)

        self.alt_label = Label(
            text="15 m",
            font_size=dp(14),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'right': 0.95, 'top': 0.6},
            size_hint=(0.4, 0.25),
            halign='right'
        )
        info_card.add_widget(self.alt_label)

        # Mode
        self.mode_label = Label(
            # « Satellites: 8 » était inventé : le GPS NEO-6M n'est pas
            # encore branché, la position est simulée — on le dit.
            text="Mode: Normal | GPS simulé (module non branché)",
            font_size=dp(11),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'x': 0.05, 'y': 0.1},
            size_hint=(0.9, 0.2),
            halign='left'
        )
        info_card.add_widget(self.mode_label)

        info_card.bg_color.rgba = theme_manager.get_with_alpha("background", 0.93)
        _opaque_backdrop(info_card)
        main.add_widget(info_card)
        self._info_card = info_card

        # ─── BOUTONS MODE ─────────────────────────────────────────
        btn_layout = BoxLayout(
            size_hint=(0.95, None),
            height=dp(45),
            pos_hint={'center_x': 0.5, 'y': 0.02},
            spacing=dp(10)
        )

        modes = [
            ("Normal", "normal"),
            ("Marche", "walk"),
            ("Conduite", "drive"),
            ("Centrer", "center"),
        ]

        self._mode_buttons = {}
        for text, mode in modes:
            btn = NeonButton(
                text=text,
                size_hint=(1, 1),
                corner_radius=dp(2)
            )
            btn.bind(on_press=lambda x, m=mode: self._set_mode(m))
            btn_layout.add_widget(btn)
            if mode != "center":
                self._mode_buttons[mode] = btn
        self._mark_active_mode()

        _opaque_backdrop(btn_layout)
        main.add_widget(btn_layout)

        # ─── PASTILLE D'ÉTAT : LOCAL / EN LIGNE / INDISPONIBLE ─────
        # Avant, rien n'indiquait d'où venait la carte : une panne des
        # serveurs locaux passait inaperçue tant qu'il y avait internet.
        # Coin bas-droit de la zone carte visible (au-dessus du panneau info).
        # Un appui affiche le détail des trois services.
        self.status_badge = Button(
            text="", font_size=dp(12), bold=True,
            size_hint=(None, None), size=(dp(132), dp(44)),
            pos_hint={'right': 0.98, 'y': 0.385},
            background_normal="", background_down="",
            background_color=theme_manager.get_with_alpha("background", 0.9),
        )
        self.status_badge.bind(on_press=lambda *_: self._show_services_detail())
        main.add_widget(self.status_badge)
        self._refresh_status_badge()

        # L'en-tête (RETOUR + titre) du base_app est ajouté AVANT la carte,
        # donc la carte le recouvre visuellement. On remonte l'en-tête au
        # premier plan pour qu'il reste visible par-dessus la carte.
        self._raise_header()

    def _raise_header(self):
        """Redessine l'en-tête du base_app par-dessus la carte."""
        root = self.children[0]
        # Le column du base_app (en-tête + contenu) est le premier enfant ajouté
        for child in list(root.children):
            # on cherche le BoxLayout vertical du base_app (celui qui contient
            # l'en-tête) : c'est celui qui n'est pas la carte ni nos widgets
            from kivy.uix.boxlayout import BoxLayout
            if isinstance(child, BoxLayout) and child.orientation == "vertical":
                root.remove_widget(child)
                root.add_widget(child)   # ré-ajouté en dernier = au premier plan
                break

    # ─── NOUVEAU : nettoyage de la route avant chaque calcul ──
    def clear_route(self):
        """Supprime la couche de route précédente du canvas."""
        if hasattr(self.map_widget, 'clear_route'):
            self.map_widget.clear_route()
        else:
            # Fallback : on tente de supprimer la couche de route si MapView a une méthode
            try:
                self.map_widget.remove_route_layer()
            except AttributeError:
                pass
        # On supprime aussi les marqueurs de départ/arrivée pour éviter les confusions
        if hasattr(self.map_widget, 'set_markers'):
            self.map_widget.set_markers([])

    def _on_search(self, instance):
        """Lance la recherche de destination puis le calcul d'itinéraire."""
        query = self.search_input.text.strip()
        if not query:
            return
        # Effacer l'ancienne route immédiatement (sur l'interface)
        self.clear_route()
        self.nav_info.opacity = 1
        self.nav_info.text = "Recherche de « {} »...".format(query)
        # Travail réseau en arrière-plan pour ne pas figer l'écran
        import threading
        threading.Thread(target=self._do_search, args=(query,), daemon=True).start()

    def _do_search(self, query):
        """Géocodage (trouver le lieu) puis routage (tracer le trajet)."""
        from kivy.clock import Clock
        from nova import navigation

        results = navigation.geocode(query, country="tn")
        # Cas quota MapTiler dépassé
        if isinstance(results, dict) and results.get("error") == "quota":
            Clock.schedule_once(
                lambda dt: self._set_nav_info(
                    "Quota carte dépassé. Attendez une minute et réessayez."), 0)
            return
        if not results:
            # navigation dit POURQUOI : serveur local en panne ou vraiment
            # aucun résultat — les deux ne se corrigent pas pareil.
            msg = navigation.last_failure() or "Aucun résultat pour cette recherche."
            Clock.schedule_once(lambda dt: self._set_nav_info(msg), 0)
            return

        dest = results[0]
        dlat, dlon = dest["lat"], dest["lon"]

        # Départ = position GPS actuelle
        slat, slon = self.latitude, self.longitude

        # Placer les marqueurs (départ turquoise, arrivée rouge) et centrer
        def show_markers(dt):
            self.map_widget.set_markers([
                (slat, slon, (0.0, 0.94, 1.0)),   # position (départ)
                (dlat, dlon, (0.95, 0.2, 0.2)),   # destination (arrivée)
            ])
            self.map_widget.set_center(dlat, dlon)
        Clock.schedule_once(show_markers, 0)

        # Calculer le vrai trajet par les routes (le profil suit le mode actif)
        r = navigation.route(slat, slon, dlat, dlon, profile=self._profile_for_mode())
        if r and r.get("points"):
            # Route valide : on l'affiche
            def show_route(dt):
                # On efface à nouveau pour être sûr (au cas où)
                self.clear_route()
                self.map_widget.set_route(r["points"])
                self._set_nav_info(
                    "[b]{}[/b]  ·  {:.1f} km  ·  {:.0f} min".format(
                        dest["name"][:40], r["distance_km"], r["duration_min"]))
                # mémoriser le trajet et proposer le bouton Démarrer
                self._current_route = r
                self._current_dest = dest
                self._show_start_button()
            Clock.schedule_once(show_route, 0)
        else:
            # Pas de route : on affiche un message d'erreur, on ne trace PAS de ligne droite
            reason = navigation.last_failure() or "Impossible de calculer l'itinéraire."

            def show_error(dt):
                self._set_nav_info(reason)
                # On s'assure qu'aucune route n'est affichée
                self.clear_route()
                self._current_route = None
                self._current_dest = None
            Clock.schedule_once(show_error, 0)

    def _set_nav_info(self, text):
        self.nav_info.opacity = 1
        self.nav_info.text = text

    def on_enter(self, *args):
        """À l'ouverture de Maps : simulation de position + état des services."""
        if self._movement_clock is None:
            self._movement_clock = Clock.schedule_interval(self._simulate_movement, 2.0)

        from nova.map_services import get_map_services
        services = get_map_services()
        # Normalement déjà lancé par main.on_start ; idempotent sinon.
        services.start()
        if self._services_listener is None:
            # Le gestionnaire notifie depuis son thread : on repasse sur le
            # thread graphique Kivy avant de toucher aux widgets.
            self._services_listener = lambda snap: Clock.schedule_once(
                lambda dt: self._on_services_changed(), 0)
            services.add_listener(self._services_listener)
        self._on_services_changed()

    def on_leave(self, *args):
        """À la sortie de Maps : arrêter la simulation de position.
        Les serveurs de carte, eux, restent actifs : les supprimer à chaque
        sortie était la cause du bug « carte hors ligne cassée »."""
        if self._movement_clock is not None:
            self._movement_clock.cancel()
            self._movement_clock = None
        if self._services_listener is not None:
            from nova.map_services import get_map_services
            get_map_services().remove_listener(self._services_listener)
            self._services_listener = None

    # ─── État des services hors ligne ──────────────────────────
    def _map_mode(self):
        """(mode, couleur) de la carte : local / démarrage / en ligne /
        indisponible, d'après la config et l'état RÉEL du serveur de tuiles."""
        from nova.utils.config_loader import get_config
        from nova.map_services import get_map_services, READY, STARTING
        cfg = get_config().get("map", {}) or {}
        if cfg.get("provider", "") != "local":
            return "en ligne", "warning"   # choix explicite de la config
        snap = get_map_services().snapshot()
        tiles = snap["tiles"][0]
        if tiles == READY:
            partiel = any(v[0] != READY for v in snap.values())
            return ("local (partiel)" if partiel else "local"), (
                "warning" if partiel else "success")
        if tiles == STARTING:
            return "démarrage", "warning"
        if cfg.get("allow_online_fallback", False):
            return "en ligne", "warning"
        return "indisponible", "error"

    def _refresh_status_badge(self):
        mode, color = self._map_mode()
        # Pas de pastille « ● » : ce caractère n'existe pas dans la police
        # embarquée et s'affichait en carré vide. C'est le texte lui-même
        # qui prend la couleur de l'état.
        self.status_badge.text = mode.upper()
        self.status_badge.color = theme_manager.get_color(color)

    def _on_services_changed(self):
        """Réagit à un changement d'état : pastille, tuiles, message."""
        mode, _c = self._map_mode()
        self._refresh_status_badge()

        want_online = mode == "en ligne"
        if want_online != self._online_tiles or (mode.startswith("local")
                                                 and not self._map_ready):
            self._switch_tiles(online=want_online)
        self._map_ready = mode.startswith("local") or want_online

        if mode == "démarrage":
            self._set_nav_info("Démarrage de la carte hors ligne...")
        elif mode == "indisponible":
            from nova.map_services import get_map_services
            reason = get_map_services().status("tiles")[1]
            self._set_nav_info("Carte hors ligne indisponible : " + reason)
        elif self.nav_info.text.startswith(("Démarrage de la carte",
                                            "Carte hors ligne indisponible")):
            self.nav_info.text = ""
            self.nav_info.opacity = 0

    def _switch_tiles(self, online):
        """Change la source des tuiles et recharge l'affichage.
        Les tuiles internet ont leur propre cache disque, pour ne pas se
        mélanger avec celles du serveur local (styles différents)."""
        from nova.paths import MAP_TILES_DIR
        from nova.ui.map_engine import build_tile_url
        if online:
            cfg = {"map": {"provider": "maptiler"}}
            try:
                from nova.utils.config_loader import get_config
                cfg = {"map": dict(get_config().get("map", {}) or {},
                                   provider="maptiler")}
            except Exception:
                pass
            self.map_widget.tile_url = build_tile_url(cfg)
            self.map_widget.tiles_dir = str(MAP_TILES_DIR / "online")
            print("[maps] tuiles EN LIGNE (repli autorisé par la config)")
        else:
            self.map_widget.tile_url = build_tile_url()
            self.map_widget.tiles_dir = str(MAP_TILES_DIR)
        self._online_tiles = online
        self.map_widget._tile_cache.clear()
        self.map_widget._missing.clear()
        self.map_widget._redraw()

    def _show_services_detail(self):
        """Affiche l'état de chaque service (appui sur la pastille)."""
        from nova.map_services import get_map_services, READY, STARTING
        noms = {READY: "prêt", STARTING: "démarrage"}
        lignes = []
        for state, reason, label in get_map_services().snapshot().values():
            txt = noms.get(state, "INDISPONIBLE")
            lignes.append("{} : {}{}".format(label, txt,
                                             " — " + reason if reason else ""))
        self._set_nav_info("\n".join(lignes))

    def _show_start_button(self):
        """Affiche le bouton Démarrer une fois un trajet trouvé."""
        if self._start_btn is not None:
            return   # déjà affiché
        main = self.children[0]
        self._start_btn = NeonButton(
            icon="explore", text="Démarrer",
            size_hint=(0.5, None), height=dp(40),
            pos_hint={'center_x': 0.5, 'y': 0.09},
            corner_radius=dp(2), accent="primary")
        self._start_btn.bind(on_press=lambda x: self._start_navigation())
        main.add_widget(self._start_btn)

    def _hide_start_button(self):
        if self._start_btn is not None:
            self.children[0].remove_widget(self._start_btn)
            self._start_btn = None

    def _start_navigation(self):
        """Lance le guidage : mode navigation + première instruction."""
        if not self._current_route:
            return
        self._nav_active = True
        self._nav_step = 0
        self._hide_start_button()

        # Masquer l'info panel (coordonnées/vitesse) pendant le guidage
        if hasattr(self, "_info_card"):
            self._info_card.opacity = 0

        # Zoomer sur le trajet (vue navigation rapprochée)
        self.map_widget.set_zoom(16)
        self.map_widget.set_center(self.latitude, self.longitude)

        # Afficher la première instruction
        self._show_current_step()

        # Bouton pour passer à l'étape suivante (en attendant le vrai GPS
        # qui fera avancer les étapes automatiquement selon la position)
        if self._nav_btn is None:
            main = self.children[0]
            self._nav_btn = NeonButton(
                icon="chevron_right", text="Suivant",
                size_hint=(0.4, None), height=dp(40),
                pos_hint={'center_x': 0.42, 'y': 0.09},
                corner_radius=dp(2), accent="primary")
            self._nav_btn.bind(on_press=lambda x: self._next_step())
            main.add_widget(self._nav_btn)
        # Bouton pour arrêter le guidage
        if self._stop_nav_btn is None:
            main = self.children[0]
            self._stop_nav_btn = NeonButton(
                icon="close", text="Arrêter",
                size_hint=(0.35, None), height=dp(40),
                pos_hint={'center_x': 0.8, 'y': 0.09},
                corner_radius=dp(2), accent="primary")
            self._stop_nav_btn.bind(on_press=lambda x: self._stop_navigation())
            main.add_widget(self._stop_nav_btn)

    def _stop_navigation(self):
        """Arrête le guidage et revient à la vue normale."""
        self._nav_active = False
        for btn_attr in ("_nav_btn", "_stop_nav_btn"):
            btn = getattr(self, btn_attr, None)
            if btn is not None:
                self.children[0].remove_widget(btn)
                setattr(self, btn_attr, None)
        self.nav_info.text = ""
        self.nav_info.opacity = 0
        self.map_widget.set_zoom(14)
        # Réafficher l'info panel
        if hasattr(self, "_info_card"):
            self._info_card.opacity = 1

    def _show_current_step(self):
        """Affiche l'instruction de virage courante."""
        steps = self._current_route.get("steps", []) if self._current_route else []
        if not steps:
            self._set_nav_info("Guidage lancé — suivez le trajet en bleu.")
            return
        if self._nav_step >= len(steps):
            self._set_nav_info("[b]Arrivée à destination[/b]")
            self._nav_active = False
            # retirer le bouton Suivant, garder le bouton fermer un instant
            if self._nav_btn is not None:
                self.children[0].remove_widget(self._nav_btn)
                self._nav_btn = None
            return
        step = steps[self._nav_step]
        instr = step["instruction"]
        dist = step["distance"]
        # Formuler l'étape
        if dist >= 1000:
            dtxt = "{:.1f} km".format(dist / 1000.0)
        else:
            dtxt = "{:.0f} m".format(dist)
        self._set_nav_info("[b]{}[/b]  ({})   [{}/{}]".format(
            instr, dtxt, self._nav_step + 1, len(steps)))

    def _next_step(self):
        """Passe à l'instruction suivante (manuel pour l'instant, GPS plus tard)."""
        if not self._nav_active:
            return
        self._nav_step += 1
        self._show_current_step()

    def _simulate_movement(self, dt):
        """Simule un déplacement (sera remplacé par le vrai GPS NEO-6M sur le Pi)."""
        from nova.utils.platform_utils import is_raspberry_pi
        if is_raspberry_pi():
            # Emplacement pour la lecture réelle du GPS (module NEO-6M) :
            #   lat, lon, speed, alt = read_gps()
            pass
        else:
            self.latitude += random.gauss(0, 0.00005)
            self.longitude += random.gauss(0, 0.00005)
            self.speed = abs(random.gauss(5, 3))
            self.altitude = 15 + random.gauss(0, 2)

        self.coord_label.text = f"{self.latitude:.4f}°N  {self.longitude:.4f}°E"
        self.speed_label.text = f"{self.speed:.1f} km/h"
        self.alt_label.text = f"{self.altitude:.0f} m"

        # Marqueur de position sur la vraie carte (point turquoise)
        if hasattr(self, "map_widget"):
            self.map_widget.set_markers(
                [(self.latitude, self.longitude, (0.0, 0.94, 1.0))])
            # Marche/Conduite : la carte suit la position (on est en mouvement).
            # Normal : on laisse l'utilisateur cadrer librement.
            if self.mode in ("walk", "drive"):
                self.map_widget.set_center(self.latitude, self.longitude)

    # Cahier des charges Phase 6 : "Mode normal" (navigation classique, vue
    # d'ensemble) vs "Mode personnalise" (interface minimaliste adaptee au
    # deplacement). Chaque mode a un vrai comportement distinct : zoom,
    # suivi automatique de la position, et profil de routage.
    _ZOOM_PAR_MODE = {"normal": 14, "walk": 17, "drive": 15}
    _PROFIL_PAR_MODE = {"normal": "driving-car", "walk": "foot-walking", "drive": "driving-car"}
    _LIBELLE_MODE = {"normal": "Mode normal", "walk": "Mode marche (pieton)",
                     "drive": "Mode conduite"}

    def _set_mode(self, mode):
        """Change le mode d'affichage/navigation."""
        print(f"[maps] Mode : {mode}")
        if mode == "center":
            if hasattr(self, "map_widget"):
                self.map_widget.set_center(self.latitude, self.longitude)
            return

        if mode not in self._ZOOM_PAR_MODE:
            return
        changement = mode != self.mode
        self.mode = mode
        self._mark_active_mode()

        if hasattr(self, "map_widget"):
            self.map_widget.set_zoom(self._ZOOM_PAR_MODE[mode])
            # Marche/Conduite : on se deplace, la carte doit suivre.
            # Normal : vue d'ensemble, on laisse l'utilisateur cadrer lui-meme.
            if mode in ("walk", "drive"):
                self.map_widget.set_center(self.latitude, self.longitude)

        if changement and not self._nav_active:
            self._set_nav_info(self._LIBELLE_MODE[mode])
            Clock.schedule_once(lambda *_a: self._clear_transient_info(), 1.6)

        # Un trajet est deja affiche : le recalculer avec le profil du
        # nouveau mode (a pied vs en voiture change vraiment l'itineraire).
        if self._current_dest is not None and changement:
            self._recompute_route_for_mode()

    def _clear_transient_info(self):
        """Efface le message de mode si rien de plus important ne l'a remplace."""
        if self.nav_info.text in self._LIBELLE_MODE.values():
            self.nav_info.text = ""
            self.nav_info.opacity = 0

    def _mark_active_mode(self):
        """Met en evidence le bouton du mode actif (bordure accentuee)."""
        for cle, btn in getattr(self, "_mode_buttons", {}).items():
            actif = cle == self.mode
            btn.border_width = 2.4 if actif else 1.2
            btn._refresh()

    def _profile_for_mode(self):
        return self._PROFIL_PAR_MODE.get(self.mode, "driving-car")

    def _recompute_route_for_mode(self):
        """Recalcule l'itineraire courant avec le profil du mode actif."""
        from nova import navigation

        dest = self._current_dest
        slat, slon = self.latitude, self.longitude
        dlat, dlon = dest["lat"], dest["lon"]
        profil = self._profile_for_mode()

        def travailler():
            r = navigation.route(slat, slon, dlat, dlon, profile=profil)
            if not r or not r.get("points"):
                return

            def appliquer(dt):
                self.map_widget.set_route(r["points"])
                self._current_route = r
                self._set_nav_info(
                    "[b]{}[/b]  ·  {:.1f} km  ·  {:.0f} min  ·  {}".format(
                        dest["name"][:40], r["distance_km"], r["duration_min"],
                        self._LIBELLE_MODE[self.mode]))
            Clock.schedule_once(appliquer, 0)

        import threading
        threading.Thread(target=travailler, daemon=True).start()


NovaApp = MapsApp
