#!/usr/bin/env python3
"""Navigation pour NOVA : recherche de lieu + calcul d'itinéraire.

Deux services (chacun avec sa clé dans la config) :

  - Géocodage (chercher un lieu par son nom)  -> MapTiler
      https://api.maptiler.com/geocoding/{recherche}.json?key=CLE
  - Routage (calculer le trajet A -> B)        -> OpenRouteService
      https://api.openrouteservice.org/v2/directions/{profil}/geojson

Les appels réseau sont faits en arrière-plan par l'app (thread), pour ne pas
figer l'interface. Ici on ne fait que construire les requêtes et interpréter
les réponses.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "NOVA-Wearable/1.0 (personal project)"

# Nominatim (recherche officielle OSM) : le meilleur pour trouver les commerces,
# écoles, restaurants. Gratuit, sans clé, mais LIMITE STRICTE de 1 requête/seconde.
_last_nominatim_call = [0.0]


def _nominatim_search(query, country="tn", limit=5):
    """Recherche via Nominatim (OSM). Trouve bien les points d'intérêt.

    Respecte la limite de 1 req/s imposée par le service public.
    Renvoie une liste [{"name","lat","lon"}] ou [] si rien.
    """
    if not query.strip():
        return []
    # respecter le 1 req/s
    elapsed = time.time() - _last_nominatim_call[0]
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    _last_nominatim_call[0] = time.time()

    params = {
        "q": query.strip(),
        "format": "json",
        "limit": str(limit),
        "countrycodes": country,        # filtre strict sur le pays
        "accept-language": "fr,ar,en",  # gère le mélange de langues
        "addressdetails": "1",
    }
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as error:
        print("[nav] Nominatim indisponible :", error)
        return []

    results = []
    for item in data:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, ValueError):
            continue
        name = item.get("display_name", query)
        results.append({"name": name, "lat": lat, "lon": lon})
    return results


def _map_config():
    try:
        from nova.utils.config_loader import get_config
        return get_config().get("map", {}) or {}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Géocodage : nom de lieu -> coordonnées (MapTiler)
# ─────────────────────────────────────────────────────────────────────────────
def _nominatim_local_search(query, country="tn", limit=5):
    """Recherche via TON serveur Nominatim local (Docker, hors ligne).

    Aucune limite de débit ici : c'est ta propre machine.
    Renvoie [] si le serveur local n'est pas joignable (pas encore lancé).
    """
    if not query.strip():
        return []
    cfg = _map_config()
    url_base = cfg.get("nominatim_local_url", "http://localhost:8088")
    params = {
        "q": query.strip(),
        "format": "json",
        "limit": str(limit),
        "countrycodes": country,
        "accept-language": "fr,ar,en",
        "addressdetails": "1",
    }
    url = url_base.rstrip("/") + "/search?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as error:
        print("[nav] Nominatim local indisponible ({}), repli en ligne".format(error))
        return []

    results = []
    for item in data:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, ValueError):
            continue
        name = item.get("display_name", query)
        results.append({"name": name, "lat": lat, "lon": lon})
    return results


def geocode(query, country="tn", limit=5):
    """Cherche un lieu par son nom. Renvoie une liste de résultats :
    [{"name": ..., "lat": ..., "lon": ...}, ...] (vide si rien / erreur).

    Stratégie, du plus au moins prioritaire :
      1. Nominatim LOCAL (ton serveur Docker, 100% hors ligne)
      2. Nominatim public (en ligne, si le serveur local est indisponible)
      3. MapTiler (secours final)
    """
    if not query.strip():
        return []

    # 1) Nominatim LOCAL : hors ligne, aucune limite de débit
    results = _nominatim_local_search(query, country=country, limit=limit)
    if results:
        return results

    # 2) Nominatim public (OSM en ligne) : bon pour les points d'intérêt
    results = _nominatim_search(query, country=country, limit=limit)
    if results:
        return results

    # 3) Secours final : MapTiler (bon pour adresses/rues/villes)
    return _maptiler_search(query, country=country, limit=limit)


def _maptiler_search(query, country="tn", limit=5):
    """Recherche via MapTiler (secours). Bon pour adresses, rues, villes."""
    cfg = _map_config()
    key = cfg.get("api_key", "")
    if not key or not query.strip():
        return []

    q = urllib.parse.quote(query.strip())
    url = ("https://api.maptiler.com/geocoding/{}.json?key={}&limit={}"
           .format(q, key, limit))
    if country:
        url += "&country={}".format(country)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 429:
            print("[nav] géocodage : quota MapTiler dépassé (429).")
            return {"error": "quota"}
        print("[nav] géocodage MapTiler impossible :", error)
        return []
    except Exception as error:
        print("[nav] géocodage MapTiler impossible :", error)
        return []

    results = []
    for feature in data.get("features", []):
        center = feature.get("center") or feature.get("geometry", {}).get("coordinates")
        if not center or len(center) < 2:
            continue
        lon, lat = center[0], center[1]
        name = feature.get("place_name") or feature.get("text") or query
        results.append({"name": name, "lat": lat, "lon": lon})
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Routage : A -> B -> tracé du trajet (OpenRouteService)
# ─────────────────────────────────────────────────────────────────────────────
def _decode_polyline6(encoded):
    """Décode une polyline Valhalla (précision 6 décimales) en liste (lat, lon).

    Algorithme officiel Valhalla : https://valhalla.github.io/valhalla/decoding/
    """
    inv = 1.0 / 1e6
    decoded = []
    previous = [0, 0]
    i = 0
    length = len(encoded)
    while i < length:
        ll = [0, 0]
        for j in [0, 1]:
            shift = 0
            result = 0
            while True:
                byte = ord(encoded[i]) - 63
                i += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            ll[j] = previous[j] + delta
            previous[j] = ll[j]
        decoded.append((ll[0] * inv, ll[1] * inv))  # (lat, lon)
    return decoded


def route(start_lat, start_lon, end_lat, end_lon, profile="driving-car"):
    """Calcule l'itinéraire entre deux points.

    Renvoie un dict :
      {"points": [(lat, lon), ...], "distance_km": ..., "duration_min": ...}
    ou None si échec (aucun moteur disponible, aucun trajet).

    Stratégie : Valhalla LOCAL d'abord (hors ligne, pas de clé, pas de quota),
    puis OpenRouteService (en ligne) si Valhalla ne répond pas.

    Bug observé (ligne droite affichée sur la carte) : juste après le
    démarrage du conteneur Valhalla, son serveur HTTP répond déjà sur
    /status alors que ses tuiles routières sont encore en cours de
    construction en arrière-plan — un appel /route pendant cette fenêtre
    renvoie parfois un trajet dégradé à seulement 2 points (départ ->
    arrivée), que la carte trace comme une ligne droite au lieu d'un vrai
    itinéraire. _route_valhalla rejette déjà ce cas (voir plus bas), donc il
    est traité ici comme un échec ; on retente une fois après une courte
    pause avant de basculer sur ORS, pour absorber ce délai de démarrage
    sans obliger l'utilisateur à redémarrer le conteneur à la main.
    """
    for tentative in range(2):
        result = _route_valhalla(start_lat, start_lon, end_lat, end_lon, profile)
        if result is not None:
            return result
        if tentative == 0:
            time.sleep(2)
    return _route_ors(start_lat, start_lon, end_lat, end_lon, profile)


def _route_valhalla(start_lat, start_lon, end_lat, end_lon, profile="driving-car"):
    """Routage via le moteur Valhalla local (Docker, hors ligne)."""
    cfg = _map_config()
    url = cfg.get("valhalla_url", "http://localhost:8002/route")

    # Valhalla utilise ses propres noms de profils
    costing = {"driving-car": "auto", "foot-walking": "pedestrian",
               "cycling-regular": "bicycle"}.get(profile, "auto")

    body = json.dumps({
        "locations": [
            {"lat": start_lat, "lon": start_lon},
            {"lat": end_lat, "lon": end_lon},
        ],
        "costing": costing,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as error:
        print("[nav] Valhalla local indisponible ({}), repli en ligne".format(error))
        return None

    try:
        trip = data["trip"]
        legs = trip["legs"]
        points = []
        for leg in legs:
            points.extend(_decode_polyline6(leg["shape"]))
        # Un vrai trajet routier suit les rues et compte presque toujours
        # plus de 2 points ; Valhalla renvoie un trajet dégradé à 2 points
        # (départ -> arrivée, tracé en ligne droite par la carte) quand ses
        # tuiles ne sont pas encore chargées, juste après le démarrage du
        # conteneur. On le traite comme un échec plutôt que d'afficher une
        # fausse ligne droite : route() retentera puis basculera sur ORS.
        if len(points) < 3:
            print("[nav] Valhalla : trajet dégradé ({} point(s)), tuiles "
                  "probablement pas encore chargées.".format(len(points)))
            return None
        summary = trip.get("summary", {})
        dist_km = summary.get("length", 0)          # déjà en km chez Valhalla
        dur_min = summary.get("time", 0) / 60.0
        return {"points": points, "distance_km": dist_km, "duration_min": dur_min}
    except (KeyError, IndexError) as error:
        print("[nav] réponse Valhalla inattendue :", error)
        return None


def _route_ors(start_lat, start_lon, end_lat, end_lon, profile="driving-car"):
    """Routage via OpenRouteService (en ligne, secours si Valhalla indisponible)."""
    cfg = _map_config()
    ors_key = cfg.get("ors_key", "")
    if not ors_key:
        return None

    url = ("https://api.openrouteservice.org/v2/directions/{}/geojson"
           .format(profile))
    body = json.dumps({
        # ORS attend [lon, lat]
        "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
    }).encode("utf-8")

    headers = {
        "Authorization": ors_key,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }

    try:
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as error:
        print("[nav] routage en ligne impossible :", error)
        return None

    features = data.get("features", [])
    if not features:
        return None
    feat = features[0]
    coords = feat.get("geometry", {}).get("coordinates", [])
    # GeoJSON LineString : [[lon, lat], ...] -> on veut [(lat, lon), ...]
    points = [(c[1], c[0]) for c in coords if len(c) >= 2]
    if len(points) < 3:
        # Même garde-fou que pour Valhalla : un trajet à 2 points se
        # traçerait comme une ligne droite plutôt qu'un vrai itinéraire.
        print("[nav] ORS : trajet dégradé ({} point(s)).".format(len(points)))
        return None

    summary = feat.get("properties", {}).get("summary", {})
    dist_km = summary.get("distance", 0) / 1000.0
    dur_min = summary.get("duration", 0) / 60.0

    # Instructions de virage étape par étape (pour le guidage)
    steps = []
    segments = feat.get("properties", {}).get("segments", [])
    for seg in segments:
        for step in seg.get("steps", []):
            steps.append({
                "instruction": step.get("instruction", ""),
                "distance": step.get("distance", 0),   # mètres
                "duration": step.get("duration", 0),   # secondes
                "name": step.get("name", ""),          # nom de la rue
            })

    return {"points": points, "distance_km": dist_km,
            "duration_min": dur_min, "steps": steps}


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance à vol d'oiseau (repli si le routage échoue)."""
    import math
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))
