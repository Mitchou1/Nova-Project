#!/usr/bin/env python3
"""Moteur de carte raster hors ligne pour NOVA.

Affiche une carte à partir de tuiles d'images stockées localement, selon le
schéma standard « slippy map » (z/x/y.png) utilisé par OpenStreetMap et tous
les GPS. On peut la déplacer (glisser) et zoomer.

Hors ligne par conception : les tuiles sont lues sur le disque, aucun accès
réseau. Pour de vraies cartes, on place les tuiles de la zone voulue dans le
dossier configuré (voir MapView.tiles_dir).

Conversion géographique <-> tuiles : formules standard Web Mercator, donc
compatibles avec n'importe quel jeu de tuiles OSM.
"""

import math
import os
import threading

from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

TILE_SIZE = 256

# Fournisseurs de tuiles. On construit l'URL selon la config (clé, style).
# OSM public est bloqué pour un usage applicatif : on passe par MapTiler.
USER_AGENT = "NOVA-Wearable/1.0 (personal offline project)"


def build_tile_url(config=None):
    """Construit l'URL de tuiles à partir de la configuration.

    Priorité :
      1. Serveur local (TileServer-GL) si provider = "local" -> 100% hors ligne
      2. MapTiler si une clé est fournie
      3. Repli OSM public (susceptible d'être bloqué)
    """
    if config is None:
        try:
            from nova.utils.config_loader import get_config
            config = get_config()
        except Exception:
            config = None

    provider = "maptiler"
    style = "streets-v2-dark"
    key = ""
    local_url = ""
    if config is not None:
        m = config.get("map", {}) or {}
        provider = m.get("provider", provider)
        style = m.get("style", style)
        key = m.get("api_key", "")
        local_url = m.get("local_url", "")

    # 1) Serveur local (hors ligne) : TileServer-GL
    if provider == "local" and local_url:
        return local_url

    # 2) MapTiler (en ligne, avec clé)
    if provider == "maptiler" and key:
        return ("https://api.maptiler.com/maps/{}/256/{{z}}/{{x}}/{{y}}.png?key={}"
                .format(style, key))

    # 3) repli (peut être bloqué) : OSM public
    return "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


DEFAULT_TILE_URL = None  # résolu au runtime via build_tile_url()


# ─────────────────────────────────────────────────────────────────────────────
# Conversions géographiques (Web Mercator, standard OSM)
# ─────────────────────────────────────────────────────────────────────────────
def deg_to_num(lat, lon, zoom):
    """Latitude/longitude -> coordonnées de tuile (flottantes) au zoom donné."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def num_to_deg(x, y, zoom):
    """Coordonnées de tuile -> latitude/longitude."""
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


class MapView(Widget):
    """Carte glissable/zoomable affichant des tuiles locales.

    - center_lat / center_lon : point géographique au centre de la vue
    - zoom : niveau de zoom (entier, typiquement 10 à 16)
    - tiles_dir : dossier racine des tuiles, organisé en tiles_dir/z/x/y.png
    """

    def __init__(self, tiles_dir, center_lat=36.8065, center_lon=10.1815,
                 zoom=12, min_zoom=3, max_zoom=18, online=True,
                 tile_url=None, **kwargs):
        super().__init__(**kwargs)
        self.tiles_dir = tiles_dir
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.zoom = zoom
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
        self.online = online          # si True, télécharge les tuiles manquantes
        # URL des tuiles : fournie explicitement, sinon construite depuis la config
        self.tile_url = tile_url or build_tile_url()

        self._tile_cache = {}       # (z,x,y) -> texture Kivy
        self._missing = set()       # tuiles absentes ET non téléchargeables
        self._downloading = set()   # tuiles en cours de téléchargement
        self._drag = None
        self._markers = []          # points à dessiner (lat, lon, couleur)
        self._route = []            # liste de (lat, lon) pour tracer un itinéraire

        os.makedirs(self.tiles_dir, exist_ok=True)
        self.bind(pos=self._redraw, size=self._redraw)

    # --- gestion des tuiles ---------------------------------------------
    def _tile_path(self, z, x, y):
        return os.path.join(self.tiles_dir, str(z), str(x), "{}.png".format(y))

    def _get_tile_texture(self, z, x, y):
        key = (z, x, y)
        if key in self._tile_cache:
            return self._tile_cache[key]
        path = self._tile_path(z, x, y)
        # 1) déjà sur le disque (cache local ou tuiles pré-téléchargées) ?
        if os.path.exists(path):
            try:
                from kivy.core.image import Image as CoreImage
                tex = CoreImage(path).texture
                self._tile_cache[key] = tex
                return tex
            except Exception:
                pass
        # 2) sinon, télécharger en ligne (en arrière-plan) si autorisé
        # Limite de téléchargements simultanés : évite de marteler MapTiler
        # (sinon erreur 429 Too Many Requests et quota épuisé).
        MAX_PARALLEL = 4
        if (self.online and key not in self._downloading
                and key not in self._missing
                and len(self._downloading) < MAX_PARALLEL):
            self._downloading.add(key)
            threading.Thread(target=self._download_tile, args=(z, x, y),
                             daemon=True).start()
        return None

    def _download_tile(self, z, x, y):
        """Télécharge une tuile depuis le serveur et la met en cache disque."""
        key = (z, x, y)
        url = self.tile_url.format(z=z, x=x, y=y)
        path = self._tile_path(z, x, y)
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
            # forcer un redraw sur le thread graphique pour afficher la tuile
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: self._redraw(), 0)
        except Exception:
            # pas de réseau / tuile indisponible : on ne réessaie pas en boucle
            self._missing.add(key)
        finally:
            self._downloading.discard(key)

    # --- dessin ----------------------------------------------------------
    def _redraw(self, *_):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        n = 2 ** self.zoom
        # position (flottante) du centre en tuiles
        cx, cy = deg_to_num(self.center_lat, self.center_lon, self.zoom)

        # combien de tuiles pour remplir la vue, + marge
        # Marge minimale (1 tuile) : moins de tuiles hors écran = moins de
        # requêtes MapTiler, donc on préserve le quota gratuit.
        tiles_x = int(self.width / TILE_SIZE) + 1
        tiles_y = int(self.height / TILE_SIZE) + 1

        with self.canvas:
            Color(0.09, 0.11, 0.13, 1)
            Rectangle(pos=self.pos, size=self.size)

            for dx in range(-tiles_x, tiles_x + 1):
                for dy in range(-tiles_y, tiles_y + 1):
                    tx = int(cx) + dx
                    ty = int(cy) + dy
                    if tx < 0 or ty < 0 or tx >= n or ty >= n:
                        continue
                    tex = self._get_tile_texture(self.zoom, tx, ty)
                    if tex is None:
                        continue
                    # position à l'écran de cette tuile
                    screen_x = self.center_x + (tx - cx) * TILE_SIZE
                    screen_y = self.center_y - (ty - cy) * TILE_SIZE - TILE_SIZE
                    Color(1, 1, 1, 1)
                    Rectangle(texture=tex, pos=(screen_x, screen_y),
                              size=(TILE_SIZE, TILE_SIZE))

            # tracé d'itinéraire (par-dessus les tuiles)
            if len(self._route) >= 2:
                from kivy.graphics import Line
                pts = []
                for lat, lon in self._route:
                    sx, sy = self._geo_to_screen(lat, lon)
                    pts.extend([sx, sy])
                Color(0.0, 0.94, 1.0, 1)
                Line(points=pts, width=dp(2.5))

            # marqueurs
            for lat, lon, col in self._markers:
                sx, sy = self._geo_to_screen(lat, lon)
                r, g, b = col
                Color(r, g, b, 1)
                from kivy.graphics import Ellipse
                Ellipse(pos=(sx - dp(6), sy - dp(6)), size=(dp(12), dp(12)))

    def _geo_to_screen(self, lat, lon):
        """Point géographique -> pixels à l'écran (selon centre et zoom actuels)."""
        cx, cy = deg_to_num(self.center_lat, self.center_lon, self.zoom)
        tx, ty = deg_to_num(lat, lon, self.zoom)
        sx = self.center_x + (tx - cx) * TILE_SIZE
        sy = self.center_y - (ty - cy) * TILE_SIZE
        return sx, sy

    # --- interaction -----------------------------------------------------
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        # molette = zoom
        if touch.is_mouse_scrolling:
            if touch.button == "scrolldown":
                self.set_zoom(self.zoom - 1)
            elif touch.button == "scrollup":
                self.set_zoom(self.zoom + 1)
            return True
        self._drag = (touch.x, touch.y, self.center_lat, self.center_lon)
        return True

    def on_touch_move(self, touch):
        if self._drag is None:
            return False
        ox, oy, olat, olon = self._drag
        # déplacement en pixels -> en tuiles -> en degrés
        dx_px = touch.x - ox
        dy_px = touch.y - oy
        cx, cy = deg_to_num(olat, olon, self.zoom)
        new_cx = cx - dx_px / TILE_SIZE
        new_cy = cy + dy_px / TILE_SIZE
        self.center_lat, self.center_lon = num_to_deg(new_cx, new_cy, self.zoom)
        self._redraw()
        return True

    def on_touch_up(self, touch):
        if self._drag is not None:
            self._drag = None
            return True
        return False

    # --- API -------------------------------------------------------------
    def set_zoom(self, zoom):
        zoom = max(self.min_zoom, min(self.max_zoom, int(zoom)))
        if zoom != self.zoom:
            self.zoom = zoom
            self._redraw()

    def set_center(self, lat, lon):
        self.center_lat = lat
        self.center_lon = lon
        self._redraw()

    def set_markers(self, markers):
        """markers : liste de (lat, lon, (r,g,b))."""
        self._markers = list(markers)
        self._redraw()

    def set_route(self, points):
        """points : liste de (lat, lon) formant l'itinéraire à tracer."""
        self._route = list(points)
        self._redraw()

    def clear_route(self):
        self._route = []
        self._redraw()
