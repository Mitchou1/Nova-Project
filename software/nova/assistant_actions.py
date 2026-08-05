#!/usr/bin/env python3
"""Actions que l'assistant NOVA peut exécuter sur la machine.

Le LLM comprend la demande de l'utilisateur et produit une commande au format
JSON. Ce module l'exécute réellement : créer un événement, lister les
événements, ouvrir une application, donner l'heure, etc.

Le flux :
  1. l'utilisateur parle
  2. le LLM reçoit sa phrase + la description des actions possibles
  3. le LLM répond, soit par une commande JSON, soit par du texte (discussion)
  4. si c'est une commande, execute_action() la réalise et renvoie une phrase
     de confirmation
"""

import json
import re
from datetime import datetime, timedelta


# Description des actions, injectée dans le prompt système du LLM.
# Le LLM lit ceci pour savoir quelles commandes il peut produire.
ACTIONS_DESCRIPTION = """Tu peux piloter tout l'appareil. Si la demande de l'utilisateur correspond a
une action ci-dessous, reponds UNIQUEMENT par un objet JSON sur une seule ligne,
sans texte autour, au format indique. Sinon, discute normalement en texte.

AGENDA
1. Ajouter un evenement (rappel = minutes avant, optionnel) :
   {"action": "ajouter_evenement", "titre": "<texte>", "date": "AAAA-MM-JJ", "heure": "HH:MM", "description": "<texte>", "rappel": <nombre>}
2. Voir les evenements d'un jour :
   {"action": "voir_evenements", "date": "AAAA-MM-JJ"}
3. Supprimer les evenements d'un jour :
   {"action": "supprimer_evenements", "date": "AAAA-MM-JJ"}
4. Modifier un evenement :
   {"action": "modifier_evenement", "date": "AAAA-MM-JJ", "titre_actuel": "<texte>", "nouvelle_heure": "HH:MM", "nouveau_titre": "<texte>"}
5. Prochain evenement :
   {"action": "prochain_evenement"}

NAVIGATION
6. Ouvrir une application (maps, calendar, settings, radio, sensors, assistant) :
   {"action": "ouvrir_app", "app": "<nom>"}
7. Revenir a l'accueil :
   {"action": "accueil"}
8. Calculer un itineraire vers un lieu :
   {"action": "naviguer", "destination": "<lieu>"}
9. Position GPS actuelle :
   {"action": "ma_position"}

REGLAGES
10. Regler le volume (0 a 100) :
   {"action": "regler_volume", "valeur": <nombre>}
11. Regler la luminosite (0 a 100) :
   {"action": "regler_luminosite", "valeur": <nombre>}
12. Changer le theme (classic, cyberpunk, undercover) :
   {"action": "changer_theme", "theme": "<nom>"}
13. Activer/desactiver le WiFi :
   {"action": "wifi", "actif": true}
14. Activer/desactiver le Bluetooth :
   {"action": "bluetooth", "actif": true}
15. Activer/desactiver les notifications :
   {"action": "notifications", "actif": true}

CAPTEURS
16. Lire un capteur (temperature, humidite, pression, distance, vitesse, position, accelerometre, gyroscope) :
   {"action": "lire_capteur", "capteur": "<nom>"}
17. Lire tous les capteurs :
   {"action": "etat_capteurs"}

RADIO
18. Controler la radio (scanner, arreter, monter, descendre) :
   {"action": "controler_radio", "commande": "<nom>"}
19. Regler la frequence radio en MHz :
   {"action": "regler_frequence", "valeur": <nombre>}

SYSTEME
20. Donner l'heure ou la date :
   {"action": "heure_date"}
21. Etat de la batterie :
   {"action": "batterie"}
22. Redemarrer NOVA :
   {"action": "redemarrer"}
23. Faire vibrer l'appareil (duree en millisecondes) :
   {"action": "vibrer", "duree": <nombre>}
24. Prendre une photo avec la camera :
   {"action": "prendre_photo"}

Aujourd'hui nous sommes le {today}. Pour "demain", "apres-demain", calcule la date reelle.
Reponds en francais."""


# Noms d'apps reconnus -> identifiant interne
_APP_ALIASES = {
    "maps": "maps", "carte": "maps", "cartes": "maps", "gps": "maps", "navigation": "maps",
    "agenda": "calendar", "calendrier": "calendar", "calendar": "calendar",
    "reglages": "settings", "réglages": "settings", "parametres": "settings",
    "paramètres": "settings", "settings": "settings",
    "radio": "radio",
    "capteurs": "sensors", "capteur": "sensors", "sensors": "sensors",
    "assistant": "assistant", "nova": "assistant",
}


def build_system_prompt():
    """Prompt système complet donné au LLM (avec la date du jour)."""
    today = datetime.now().strftime("%A %d %B %Y")
    base = ("Tu es NOVA, un assistant personnel embarqué, concis et utile. "
            "Tu réponds en français.\n\n")
    # On remplace le marqueur de date manuellement plutôt qu'avec .format(),
    # car ACTIONS_DESCRIPTION contient des accolades JSON que .format()
    # tenterait (à tort) d'interpréter.
    return base + ACTIONS_DESCRIPTION.replace("{today}", today)


def extract_json(text):
    """Tente d'extraire un objet JSON d'action de la réponse du LLM.

    Renvoie le dict si trouvé et valide, sinon None (= réponse en texte libre).
    """
    if not text:
        return None
    # chercher le premier { ... } plausible
    match = re.search(r"\{[^{}]*\"action\"[^{}]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict) and "action" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Exécution des actions
# ─────────────────────────────────────────────────────────────────────────────
def execute_action(data, app=None):
    """Exécute la commande JSON. Renvoie une phrase de confirmation (str)
    ou None si l'action est inconnue.

    app : référence à l'application NOVA (pour agir : agenda, navigation…).
          Peut être None (dans ce cas, certaines actions sont limitées).
    """
    action = data.get("action")

    if action == "ajouter_evenement":
        return _add_event(data, app)
    if action == "voir_evenements":
        return _list_events(data, app)
    if action == "supprimer_evenements":
        return _delete_events(data, app)
    if action == "ouvrir_app":
        return _open_app(data, app)
    if action == "heure_date":
        return _time_date()
    if action == "prochain_evenement":
        return _next_event(app)
    if action == "modifier_evenement":
        return _edit_event(data, app)
    if action == "accueil":
        return _go_home(app)
    if action == "naviguer":
        return _navigate(data, app)
    if action == "ma_position":
        return _my_position(app)
    if action == "regler_volume":
        return _set_volume(data)
    if action == "regler_luminosite":
        return _set_brightness(data)
    if action == "changer_theme":
        return _set_theme(data)
    if action == "wifi":
        return _toggle_wifi(data)
    if action == "bluetooth":
        return _toggle_bluetooth(data)
    if action == "notifications":
        return _toggle_notifications(data)
    if action == "lire_capteur":
        return _read_sensor(data, app)
    if action == "etat_capteurs":
        return _all_sensors(app)
    if action == "controler_radio":
        return _control_radio(data, app)
    if action == "regler_frequence":
        return _set_frequency(data, app)
    if action == "batterie":
        return _battery()
    if action == "redemarrer":
        return _restart()
    if action == "vibrer":
        return _vibrate(data)
    if action == "prendre_photo":
        return _take_photo(app)
    return None


def _add_event(data, app):
    titre = (data.get("titre") or "Événement").strip()
    date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    heure = data.get("heure") or "12:00"
    description = (data.get("description") or "").strip()
    try:
        from apps.calendar import storage
        storage.add_event(title=titre, date=date, time=heure,
                          description=description)
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
            date_fr = d.strftime("%d/%m")
        except ValueError:
            date_fr = date
        return "C'est noté : « {} » le {} à {}.".format(titre, date_fr, heure)
    except Exception as error:
        print("[actions] ajout événement impossible :", error)
        return "Je n'ai pas réussi à enregistrer l'événement."


def _list_events(data, app):
    date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    try:
        from apps.calendar import storage
        events = storage.get_events_for(date)
        if not events:
            return "Aucun événement prévu ce jour-là."
        parts = []
        for e in events:
            title = e.get("title") if isinstance(e, dict) else getattr(e, "title", "")
            time_ = e.get("event_time") if isinstance(e, dict) else getattr(e, "event_time", "")
            if not time_ and isinstance(e, dict):
                time_ = e.get("time", "")
            parts.append("{} à {}".format(title, time_))
        return "Ce jour-là : " + " ; ".join(parts) + "."
    except Exception as error:
        print("[actions] lecture événements impossible :", error)
        return "Je n'ai pas pu consulter l'agenda."


def _delete_events(data, app):
    """Supprime les événements d'un jour donné."""
    date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    try:
        from apps.calendar import storage
        events = storage.get_events_for(date)
        if not events:
            return "Aucun événement à supprimer ce jour-là."
        count = 0
        for e in events:
            eid = e.get("id") if isinstance(e, dict) else getattr(e, "id", None)
            if eid is not None:
                storage.delete_event(eid)
                count += 1
        return "J'ai supprimé {} événement(s).".format(count)
    except Exception as error:
        print("[actions] suppression impossible :", error)
        return "Je n'ai pas pu supprimer les événements."


def _open_app(data, app):
    name = (data.get("app") or "").lower().strip()
    app_id = _APP_ALIASES.get(name)
    if not app_id:
        return "Je ne connais pas cette application."
    # Naviguer via le gestionnaire d'écrans, sur le thread graphique
    if app is not None and getattr(app, "manager", None) is not None:
        from kivy.clock import Clock
        Clock.schedule_once(
            lambda dt: setattr(app.manager, "current", app_id), 0)
    noms = {"maps": "Maps", "calendar": "l'Agenda", "settings": "les Réglages",
            "radio": "la Radio", "sensors": "les Capteurs", "assistant": "l'Assistant"}
    return "J'ouvre {}.".format(noms.get(app_id, app_id))


def _time_date():
    now = datetime.now()
    return "Il est {} et nous sommes le {}.".format(
        now.strftime("%H:%M"), now.strftime("%d/%m/%Y"))


def _next_event(app):
    try:
        from apps.calendar import storage
        # storage fournit un libellé tout prêt du prochain événement
        label = storage.next_event_label()
        if not label or label.strip() in ("", "Aucun événement"):
            return "Vous n'avez aucun événement à venir aujourd'hui."
        return "Votre prochain événement : {}.".format(label)
    except Exception as error:
        print("[actions] prochain événement impossible :", error)
        return "Je n'ai pas pu consulter votre prochain événement."


# ═════════════════════════════════════════════════════════════════════════
# AGENDA — modification
# ═════════════════════════════════════════════════════════════════════════
def _edit_event(data, app):
    """Modifie un evenement (storage n'a pas d'update : on supprime/recree)."""
    date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    cible_titre = (data.get("titre_actuel") or "").strip().lower()
    try:
        from apps.calendar import storage
        events = storage.get_events_for(date)
        cible = None
        for e in events:
            titre = (e.get("title") if isinstance(e, dict)
                     else getattr(e, "title", "")) or ""
            if cible_titre and cible_titre in titre.lower():
                cible = e
                break
        if cible is None:
            return "Je n'ai pas trouve cet evenement ce jour-la."

        def champ(obj, cle, defaut=""):
            return obj.get(cle, defaut) if isinstance(obj, dict) else getattr(obj, cle, defaut)

        eid = champ(cible, "id", None)
        nouveau_titre = data.get("nouveau_titre") or champ(cible, "title")
        heure = champ(cible, "event_time") or champ(cible, "time")
        nouvelle_heure = data.get("nouvelle_heure") or heure
        if eid is not None:
            storage.delete_event(eid)
        storage.add_event(title=nouveau_titre, date=date, time=nouvelle_heure,
                          description=champ(cible, "description", ""))
        return "Modifie : « {} » est maintenant a {}.".format(nouveau_titre,
                                                              nouvelle_heure)
    except Exception as error:
        print("[actions] modification impossible :", error)
        return "Je n'ai pas pu modifier l'evenement."


# ═════════════════════════════════════════════════════════════════════════
# NAVIGATION
# ═════════════════════════════════════════════════════════════════════════
def _screens(app):
    """Renvoie le gestionnaire d'ecrans, quelle que soit l'app passee."""
    return getattr(app, "manager", None) if app is not None else None


def _go_home(app):
    manager = _screens(app)
    if manager is not None:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: setattr(manager, "current", "home"), 0)
    return "Retour a l'accueil."


def _navigate(data, app):
    destination = (data.get("destination") or "").strip()
    if not destination:
        return "Vers quelle destination souhaitez-vous aller ?"
    manager = _screens(app)
    if manager is not None:
        from kivy.clock import Clock

        def aller(_dt):
            manager.current = "maps"
            ecran = manager.get_screen("maps")
            if hasattr(ecran, "search_input"):
                ecran.search_input.text = destination
                if hasattr(ecran, "_on_search"):
                    ecran._on_search(ecran.search_input)
        Clock.schedule_once(aller, 0)
    return "Je calcule l'itineraire vers {}.".format(destination)


def _my_position(app):
    manager = _screens(app)
    try:
        if manager is not None:
            ecran = manager.get_screen("maps")
            lat = getattr(ecran, "latitude", None)
            lon = getattr(ecran, "longitude", None)
            if lat is not None:
                return "Vous etes a {:.4f}°N, {:.4f}°E.".format(lat, lon)
    except Exception as error:
        print("[actions] position impossible :", error)
    return "Position GPS indisponible."


# ═════════════════════════════════════════════════════════════════════════
# REGLAGES
# ═════════════════════════════════════════════════════════════════════════
def _config():
    from nova.utils.config_loader import get_config
    return get_config()


def _sur_pi():
    try:
        from nova.utils.platform_utils import is_raspberry_pi
        return is_raspberry_pi()
    except Exception:
        return False


def _valeur_0_100(data, defaut=50):
    try:
        return max(0, min(100, int(data.get("valeur", defaut))))
    except (TypeError, ValueError):
        return None


def _set_volume(data):
    valeur = _valeur_0_100(data)
    if valeur is None:
        return "Je n'ai pas compris le niveau de volume."
    try:
        cfg = _config()
        audio = dict(cfg.get("audio", {}) or {})
        audio["volume"] = valeur
        cfg.set("audio", audio)
        if _sur_pi():
            import subprocess
            subprocess.run(["amixer", "sset", "Master", "{}%".format(valeur)],
                           capture_output=True, timeout=2)
        return "Volume regle a {} %.".format(valeur)
    except Exception as error:
        print("[actions] volume :", error)
        return "Je n'ai pas pu regler le volume."


def _set_brightness(data):
    valeur = _valeur_0_100(data)
    if valeur is None:
        return "Je n'ai pas compris le niveau de luminosite."
    try:
        cfg = _config()
        audio = dict(cfg.get("audio", {}) or {})
        audio["brightness"] = valeur
        cfg.set("audio", audio)
        return "Luminosite reglee a {} %.".format(valeur)
    except Exception as error:
        print("[actions] luminosite :", error)
        return "Je n'ai pas pu regler la luminosite."


def _set_theme(data):
    theme_demande = (data.get("theme") or "").strip().lower()
    alias = {"classique": "classic", "cyber": "cyberpunk",
             "discret": "undercover", "sombre": "undercover"}
    theme_demande = alias.get(theme_demande, theme_demande)
    if theme_demande not in ("classic", "cyberpunk", "undercover"):
        return "Theme inconnu. Choisissez classic, cyberpunk ou undercover."
    try:
        from nova.ui.theme import theme_manager
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: theme_manager.set_theme(theme_demande), 0)
        _config().set("theme", theme_demande)
        return "Theme change pour {}.".format(theme_demande)
    except Exception as error:
        print("[actions] theme :", error)
        return "Je n'ai pas pu changer le theme."


def _bool_actif(data, defaut=True):
    valeur = data.get("actif", defaut)
    if isinstance(valeur, str):
        return valeur.strip().lower() in ("true", "oui", "on", "1", "actif")
    return bool(valeur)


def _toggle_wifi(data):
    actif = _bool_actif(data)
    try:
        cfg = _config()
        wifi = dict(cfg.get("wifi", {}) or {})
        wifi["auto_connect"] = actif
        cfg.set("wifi", wifi)
        if _sur_pi():
            import subprocess
            subprocess.run(["nmcli", "radio", "wifi", "on" if actif else "off"],
                           capture_output=True, timeout=3)
        return "WiFi {}.".format("active" if actif else "desactive")
    except Exception as error:
        print("[actions] wifi :", error)
        return "Je n'ai pas pu changer le WiFi."


def _toggle_bluetooth(data):
    actif = _bool_actif(data)
    try:
        _config().set("bluetooth_enabled", actif)
        if _sur_pi():
            import subprocess
            subprocess.run(["bluetoothctl", "power", "on" if actif else "off"],
                           capture_output=True, timeout=3)
        return "Bluetooth {}.".format("active" if actif else "desactive")
    except Exception as error:
        print("[actions] bluetooth :", error)
        return "Je n'ai pas pu changer le Bluetooth."


def _toggle_notifications(data):
    actif = _bool_actif(data)
    try:
        _config().set("notifications", actif)
        return "Notifications {}.".format("activees" if actif else "desactivees")
    except Exception as error:
        print("[actions] notifications :", error)
        return "Je n'ai pas pu changer les notifications."


# ═════════════════════════════════════════════════════════════════════════
# CAPTEURS
# ═════════════════════════════════════════════════════════════════════════
_ALIAS_CAPTEURS = {
    "température": "temperature", "temp": "temperature",
    "humidité": "humidite", "hum": "humidite",
    "gps": "position", "localisation": "position",
    "accelerometre": "accelerometre", "accéléromètre": "accelerometre",
    "gyroscope": "gyroscope", "gyro": "gyroscope",
}


def _lire_valeurs(app):
    """Recupere les valeurs de l'app Capteurs (simulees sur PC)."""
    manager = _screens(app)
    if manager is None:
        return {}
    try:
        ecran = manager.get_screen("sensors")
        return dict(getattr(ecran, "sensor_data", {}) or {})
    except Exception:
        return {}


def _read_sensor(data, app):
    capteur = (data.get("capteur") or "").strip().lower()
    capteur = _ALIAS_CAPTEURS.get(capteur, capteur)
    valeurs = _lire_valeurs(app)
    bme = valeurs.get("bme280", {})
    mpu = valeurs.get("mpu6050", {})
    vl53 = valeurs.get("vl53l0x", {})
    gps = valeurs.get("gps", {})

    reponses = {
        "temperature": lambda: "Il fait {} °C.".format(bme.get("temperature", "?")),
        "humidite": lambda: "L'humidite est de {} %.".format(bme.get("humidity", "?")),
        "pression": lambda: "La pression est de {} hPa.".format(bme.get("pressure", "?")),
        "distance": lambda: "Distance mesuree : {} mm.".format(vl53.get("distance", "?")),
        "vitesse": lambda: "Votre vitesse est de {} km/h.".format(gps.get("speed", "?")),
        "position": lambda: "Vous etes a {}°N, {}°E.".format(
            gps.get("latitude", "?"), gps.get("longitude", "?")),
        "accelerometre": lambda: "Acceleration X={} Y={} Z={} g.".format(
            mpu.get("accel_x", "?"), mpu.get("accel_y", "?"), mpu.get("accel_z", "?")),
        "gyroscope": lambda: "Gyroscope X={} Y={} Z={} °/s.".format(
            mpu.get("gyro_x", "?"), mpu.get("gyro_y", "?"), mpu.get("gyro_z", "?")),
    }
    fonction = reponses.get(capteur)
    if fonction is None:
        return "Je ne connais pas ce capteur."
    suffixe = "" if _sur_pi() else " (valeur simulee)"
    return fonction() + suffixe


def _all_sensors(app):
    valeurs = _lire_valeurs(app)
    bme = valeurs.get("bme280", {})
    gps = valeurs.get("gps", {})
    vl53 = valeurs.get("vl53l0x", {})
    suffixe = "" if _sur_pi() else " (valeurs simulees)"
    return ("Temperature {} °C, humidite {} %, pression {} hPa, "
            "distance {} mm, vitesse {} km/h.{}").format(
        bme.get("temperature", "?"), bme.get("humidity", "?"),
        bme.get("pressure", "?"), vl53.get("distance", "?"),
        gps.get("speed", "?"), suffixe)


# ═════════════════════════════════════════════════════════════════════════
# RADIO
# ═════════════════════════════════════════════════════════════════════════
def _control_radio(data, app):
    commande = (data.get("commande") or "").strip().lower()
    manager = _screens(app)
    ecran = None
    if manager is not None:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: setattr(manager, "current", "radio"), 0)
        try:
            ecran = manager.get_screen("radio")
        except Exception:
            ecran = None

    if ecran is not None:
        try:
            if commande in ("scanner", "scan", "demarrer"):
                if not getattr(ecran, "scanning", False):
                    boutons = [w for w in ecran.walk()
                               if getattr(w, "icon", None) == "search"]
                    if boutons:
                        ecran._toggle_scan(boutons[0])
                return "Je lance le scan des frequences."
            if commande in ("arreter", "stop"):
                if getattr(ecran, "scanning", False):
                    boutons = [w for w in ecran.walk()
                               if getattr(w, "icon", None) == "search"]
                    if boutons:
                        ecran._toggle_scan(boutons[0])
                return "Scan arrete."
            if commande in ("monter", "augmenter", "plus"):
                ecran._change_freq(1)
                return "Frequence : {:.3f} MHz.".format(ecran.frequency)
            if commande in ("descendre", "baisser", "moins"):
                ecran._change_freq(-1)
                return "Frequence : {:.3f} MHz.".format(ecran.frequency)
        except Exception as error:
            print("[actions] radio :", error)
    return "J'ouvre la radio."


def _set_frequency(data, app):
    try:
        valeur = float(data.get("valeur"))
    except (TypeError, ValueError):
        return "Je n'ai pas compris la frequence."
    manager = _screens(app)
    if manager is not None:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: setattr(manager, "current", "radio"), 0)
        try:
            ecran = manager.get_screen("radio")
            ecran._change_freq(valeur - ecran.frequency)
            return "Frequence reglee sur {:.3f} MHz.".format(ecran.frequency)
        except Exception as error:
            print("[actions] frequence :", error)
    return "Je n'ai pas pu regler la frequence."


# ═════════════════════════════════════════════════════════════════════════
# SYSTEME
# ═════════════════════════════════════════════════════════════════════════
def _battery():
    try:
        from nova.power_manager import get_battery_level
        niveau = get_battery_level()
        if niveau is not None:
            return "Batterie a {} %.".format(niveau)
    except Exception:
        pass
    suffixe = "" if _sur_pi() else " (valeur simulee)"
    return "Batterie a 82 %.{}".format(suffixe)


def _restart():
    from kivy.clock import Clock
    def _quitter(_dt):
        import os
        os._exit(42)          # code 42 : un script de lancement peut relancer
    Clock.schedule_once(_quitter, 1.2)
    return "Je redemarre NOVA."


def _vibrate(data):
    """Fait vibrer l'appareil (moteur 3V sur GPIO, cahier des charges Phase 5).

    C'est l'exemple type d'une action : on lit le parametre, on agit, on
    renvoie une phrase de confirmation que l'assistant lira a voix haute.
    """
    # 1. Lire le parametre envoye par le LLM, avec une valeur par defaut
    try:
        duree = int(data.get("duree", 300))
    except (TypeError, ValueError):
        return "Je n'ai pas compris la duree de vibration."
    duree = max(50, min(3000, duree))      # bornes de securite

    # 2. Agir reellement (uniquement si le materiel est present)
    if _sur_pi():
        try:
            import RPi.GPIO as GPIO
            import time
            BROCHE = 18                     # GPIO du moteur de vibration
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(BROCHE, GPIO.OUT)
            GPIO.output(BROCHE, GPIO.HIGH)
            time.sleep(duree / 1000.0)
            GPIO.output(BROCHE, GPIO.LOW)
        except Exception as error:
            print("[actions] vibration impossible :", error)
            return "Le moteur de vibration ne repond pas."
        return "Vibration de {} millisecondes.".format(duree)

    # 3. Sur PC : pas de moteur, on le dit honnetement
    print("[actions] (simulation) vibration de {} ms".format(duree))
    return "Vibration de {} ms (simulee, aucun moteur connecte).".format(duree)


def _take_photo(app):
    """Prend une photo avec l'app Camera (cahier des charges Phase 8)."""
    manager = _screens(app)
    if manager is None:
        return "Je ne peux pas acceder a la camera."
    try:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: setattr(manager, "current", "camera"), 0)
        ecran = manager.get_screen("camera")
        chemin = ecran.prendre_photo()
        if chemin:
            nom = chemin.split("/")[-1]
            suffixe = "" if _sur_pi() else " (simulee, aucune camera connectee)"
            return "Photo prise : {}{}".format(nom, suffixe)
        return "La prise de photo a echoue."
    except Exception as error:
        print("[actions] photo :", error)
        return "Je n'ai pas pu prendre de photo."
