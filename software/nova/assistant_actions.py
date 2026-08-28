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

import difflib
import json
import re
import unicodedata
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
9b. Changer le mode de la carte (normal, marche, conduite) :
   {"action": "regler_mode_carte", "mode": "<nom>"}

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
16. Activer le mode economie d'energie (baisse luminosite, desactive animations) :
   {"action": "mode_economie", "actif": true}
17. Desactiver le mode economie d'energie :
   {"action": "mode_economie", "actif": false}

CAPTEURS
18. Lire un capteur (temperature, humidite, pression, distance, vitesse, position, accelerometre, gyroscope) :
   {"action": "lire_capteur", "capteur": "<nom>"}
19. Lire tous les capteurs :
   {"action": "etat_capteurs"}

RADIO
20. Controler la radio (scanner, arreter, monter, descendre) :
   {"action": "controler_radio", "commande": "<nom>"}
21. Regler la frequence radio en MHz :
   {"action": "regler_frequence", "valeur": <nombre>}

SYSTEME
22. Donner l'heure ou la date :
   {"action": "heure_date"}
23. Etat de la batterie :
   {"action": "batterie"}
24. Redemarrer NOVA :
   {"action": "redemarrer"}
25. Faire vibrer l'appareil (duree en millisecondes) :
   {"action": "vibrer", "duree": <nombre>}
26. Prendre une photo avec la camera :
   {"action": "prendre_photo"}
27. Lister ce que tu sais faire (l'utilisateur demande de l'aide, ne sait pas quoi dire) :
   {"action": "aide"}
28. Chercher sur internet une information que tu ne connais pas ou qui peut avoir change
   (actualite, definition, biographie, fait recent...) :
   {"action": "rechercher_web", "requete": "<texte de la recherche>"}
29. Ouvrir le navigateur (montrer une recherche a l'ecran plutot que la dire) :
   {"action": "ouvrir_navigateur", "requete": "<texte de la recherche>"}

FICHIERS
30. Lister le contenu du dossier courant, ou d'un sous-dossier nomme (optionnel) :
   {"action": "fichiers_lister", "dossier": "<nom, optionnel>"}
31. Creer un dossier dans le dossier courant de l'app Fichiers :
   {"action": "fichiers_creer_dossier", "nom": "<nom>"}
32. Supprimer un fichier ou dossier par son nom (demande TOUJOURS une confirmation
   a l'ecran avant de supprimer reellement — ne supprime jamais en silence) :
   {"action": "fichiers_supprimer", "nom": "<nom>"}

LANGUE
33. Changer la langue de reponse (francais, anglais, arabe) :
   {"action": "changer_langue", "langue": "<nom>"}

SUGGESTIONS
34. Proposer des suggestions proactives (prochain evenement, destination frequente) :
   {"action": "suggestions"}

Pour une question factuelle a laquelle tu n'es pas sur de la reponse, ou qui peut avoir
change depuis ton entrainement, prefere "rechercher_web" plutot que d'inventer une reponse.

Si la demande ne correspond a AUCUNE action ci-dessus (par exemple discuter, repondre a
une question generale), ne renvoie jamais de JSON : reponds normalement en texte.
Si elle correspond a une action mais qu'il manque une information (ex. quelle destination,
quelle heure), pose la question en texte plutot que de deviner une valeur.

REGLE ABSOLUE : n'ecris JAMAIS une phrase qui ressemble a une confirmation ("C'est note",
"J'ajoute", "C'est fait", "Rendez-vous cree"...) sans avoir d'abord renvoye le JSON de
l'action correspondante. Le JSON est ce qui execute reellement l'action (ex. creer le
rendez-vous) ; une phrase de confirmation ecrite seule, sans JSON, NE FAIT RIEN et trompe
l'utilisateur en lui faisant croire qu'une action a eu lieu alors qu'aucune n'a ete
executee. En cas de doute sur le format exact d'une action, prefere renvoyer le JSON
(quitte a laisser un champ optionnel vide) plutot que d'ecrire une confirmation en texte.

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
    "fichiers": "files", "fichier": "files", "files": "files", "dossiers": "files",
    "camera": "camera", "caméra": "camera", "photos": "camera", "appareil": "camera",
}


# Le schema d'actions (ACTIONS_DESCRIPTION) reste toujours en francais : les
# noms d'action et cles JSON sont des identifiants fixes du code, pas du
# texte a traduire. Seule l'instruction de langue de reponse change.
_PROMPT_INTRO = {
    "fr": ("Tu es NOVA, un assistant personnel embarqué, concis et utile. "
           "Tu réponds en français.\n\n"),
    "en": ("Tu es NOVA, un assistant personnel embarqué, concis et utile. "
           "Answer the user in English. The action schema below is written "
           "in French (action names and JSON keys) — keep them exactly as "
           "given when producing a command, but write any reply to the "
           "user in English.\n\n"),
    "ar": ("Tu es NOVA, un assistant personnel embarqué, concis et utile. "
           "أجب المستخدم باللغة العربية. مخطط الإجراءات أدناه مكتوب "
           "بالفرنسية (أسماء الإجراءات ومفاتيح JSON) — احتفظ بها كما هي "
           "بالضبط عند إصدار أمر، لكن اكتب أي رد للمستخدم باللغة "
           "العربية.\n\n"),
}

_LANGUES_VALIDES = tuple(_PROMPT_INTRO)


def _current_language():
    try:
        from nova.utils.config_loader import get_config
        langue = (get_config().get("language") or "fr").strip().lower()
        return langue if langue in _LANGUES_VALIDES else "fr"
    except Exception:
        return "fr"


def build_system_prompt(language=None):
    """Prompt système complet donné au LLM (avec la date du jour).

    language: "fr"/"en"/"ar" — lue depuis la config si non fournie.
    """
    if language not in _PROMPT_INTRO:
        language = _current_language()
    today = datetime.now().strftime("%A %d %B %Y")
    base = _PROMPT_INTRO[language]
    # On remplace le marqueur de date manuellement plutôt qu'avec .format(),
    # car ACTIONS_DESCRIPTION contient des accolades JSON que .format()
    # tenterait (à tort) d'interpréter.
    return base + ACTIONS_DESCRIPTION.replace("{today}", today)


def extract_json(text):
    """Tente d'extraire un objet JSON d'action de la réponse du LLM.

    Scanne les accolades équilibrées plutôt qu'une regex plate : la regex
    d'origine (`\\{[^{}]*"action"[^{}]*\\}`) échouait dès que le JSON contenait
    un objet imbriqué. Essaie chaque « { » de départ jusqu'à en trouver un qui
    produise un objet JSON valide contenant la clé "action".

    Renvoie le dict si trouvé et valide, sinon None (= réponse en texte libre).
    """
    if not text:
        return None
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        data = json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break
                    if isinstance(data, dict) and "action" in data:
                        return data
                    break
        start = text.find("{", start + 1)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Chemin rapide (sans LLM) pour les commandes les plus frequentes
# ─────────────────────────────────────────────────────────────────────────────
# Le LLM (3B, quantifie, execute sur un Pi Zero 2 W a terme) prend plusieurs
# secondes et ne garantit jamais un JSON valide. Pour les commandes courtes et
# non-ambigues qui n'ont pas d'argument libre a extraire (ouvrir une app,
# changer de mode/theme, donner l'heure...), on les reconnait directement ici :
# reponse instantanee et 100% fiable. Tout le reste (creer un evenement,
# calculer un itineraire, discuter...) continue de passer par le LLM.

def _sans_accents(texte):
    nfkd = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_MODE_THEME_MOTS = {
    "classic": "classic", "classique": "classic",
    "cyberpunk": "cyberpunk", "cyber": "cyberpunk",
    "undercover": "undercover", "discret": "undercover",
}

_FAST_PATH_RULES = [
    (re.compile(r"\b(quelle heure|quelle est l.heure|quel jour|quelle date|"
                r"quelle est la date)\b"),
     lambda m: {"action": "heure_date"}),
    (re.compile(r"\b(^aide$|que peux.tu faire|qu.est.ce que tu sais faire|"
                r"liste des commandes|comment ca marche)\b"),
     lambda m: {"action": "aide"}),
    (re.compile(r"\b(retour a l.accueil|reviens a l.accueil|va a l.accueil|"
                r"^accueil$|^retour$|^maison$)\b"),
     lambda m: {"action": "accueil"}),
    (re.compile(r"prochain (rendez.vous|rdv|evenement)"),
     lambda m: {"action": "prochain_evenement"}),
    (re.compile(r"(niveau de batterie|batterie restante|combien de batterie|"
                r"^batterie\??$)"),
     lambda m: {"action": "batterie"}),
    (re.compile(r"(fais vibrer|^vibre\.?$|declenche.*vibration)"),
     lambda m: {"action": "vibrer"}),
    (re.compile(r"(prends? une photo|prendre une photo|declenche.*photo)"),
     lambda m: {"action": "prendre_photo"}),
    (re.compile(r"(mes fichiers|liste (?:mes |les )?fichiers|"
                r"montre (?:moi )?(?:mes |les )?fichiers)"),
     lambda m: {"action": "fichiers_lister"}),
    (re.compile(r"(?:parle|reponds|passe|switch to|speak)(?:\s+(?:en|in|to))?\s+"
                r"(francais|french|anglais|english|arabe|arabic)"),
     lambda m: {"action": "changer_langue", "langue": m.group(1)}),
    (re.compile(r"(efface (?:l.historique|la conversation)|oublie tout|"
                r"nouvelle conversation|clear history|forget everything)"),
     lambda m: {"action": "effacer_historique"}),
    (re.compile(r"(des suggestions|une suggestion|quoi de neuf|"
                r"des recommandations|suggest something)"),
     lambda m: {"action": "suggestions"}),
    # Mode économie d'énergie. Bug corrige : l'ancienne version testait
    # "on" in m.group(0), or "economie" contient deja la sous-chaine "on"
    # (éc-ON-omie) -> actif valait toujours True, meme pour "desactive le
    # mode economie" (confirme par test reel). Ici, un verbe de desactivation
    # explicite (groupe 1) force actif=False ; son absence (juste "mode
    # economie", "passe en mode economie"...) est traitee comme une
    # activation, ce qui correspond au sens naturel de la phrase. Teste
    # contre `brut` (deja passe par _sans_accents) : les variantes
    # accentuees de l'ancienne regex ne pouvaient de toute facon jamais
    # matcher, elles sont retirees ici.
    (re.compile(r"\b(desactive|desactiver|coupe|arrete)\s+(?:le\s+)?mode\s+economie|"
                r"\bmode\s+economie(?:\s+d.energie)?\b|\beconomie\s+d.energie\b"),
     lambda m: {"action": "mode_economie", "actif": not bool(m.group(1))}),
]


# ─────────────────────────────────────────────────────────────────────────────
# Ajout de rendez-vous deterministe (sans LLM)
# ─────────────────────────────────────────────────────────────────────────────
# Audit : le LLM (3B, quantifie) produit parfois une phrase de confirmation
# credible ("C'est note...") SANS le JSON d'action correspondant -> aucun
# evenement n'est reellement cree, alors que l'utilisateur croit le contraire
# (observe reellement : confirmation orale recue, mais rien en base). Comme
# pour les autres commandes frequentes, on reconnait ici directement les
# formulations les plus courantes d'ajout de rendez-vous : reponse fiable a
# 100%, sans dependre du modele. Si la phrase est ambigue (date/heure non
# reconnues), on renvoie None et l'appelant se rabat sur le LLM.

_JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi",
                  "samedi", "dimanche"]

_DATE_RELATIVE_RE = [
    (re.compile(r"\bapres.?demain\b"), 2),   # avant "demain" : sous-chaine
    (re.compile(r"\baujourd.?hui\b"), 0),
    (re.compile(r"\bdemain\b"), 1),
]

_DATE_EXPLICITE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")

# Format ISO (AAAA-MM-JJ). Doit etre teste AVANT _DATE_EXPLICITE_RE : sinon
# "2026-09-01" n'etait jamais reconnu comme un tout, mais _DATE_EXPLICITE_RE
# matchait quand meme le sous-groupe "09-01" (le "2026-" restant hors de son
# \b initial) et l'interpretait a tort comme jour=09/mois=01 -> bug confirme,
# creait un evenement le 9 janvier au lieu du 1er septembre, avec en plus
# "2026-" laisse dans le titre.
_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")

_HEURE_RE = re.compile(
    # Pas de \b final : un rendez-vous tape sans espace apres les minutes
    # ("11h30de matin", faute de frappe reelle observee) doit rester
    # reconnu — seuls les caracteres AVANT le marqueur "h"/"heures"/":"
    # comptent pour l'heure elle-meme.
    r"\b(?:a\s+)?(\d{1,2})\s*(?:h|:|heures?)\s*(\d{1,2})?")

# Mots-cles de date reconnus par tolerance aux fautes de frappe (repli, si
# aucune des regex exactes ci-dessus n'a matche). ex. "dedmain" -> "demain".
_MOTS_DATE_RELATIVE_CONNUS = {"demain": 1, "aujourdhui": 0}

_MOTS_DECLENCHEURS_EVENEMENT = re.compile(
    r"\b(?:ajoute[rz]?|cree[rz]?|planifie[rz]?|note[rz]?|"
    r"programme[rz]?|mets|mettre|prevois|prevoyez|prevoir)\s+"
    r"(?:un\s+|une\s+)?(?:rendez.vous|rdv|evenement|rappel)\b")

_RAPPELLE_MOI_RE = re.compile(r"\brappelle.moi\s+(?:de\s+|d['’]\s*)?")


def _extraire_duree_relative(reste):
    """Extrait une durée relative du type "dans X minutes/heures/jours"
    et renvoie (date_absolue, heure_absolue, span) ou (None, None, None).
    """
    match = re.search(r"\bdans\s+(\d+)\s+(minute|minutes|heure|heures|jour|jours)\b", reste)
    if not match:
        return None, None, None
    valeur = int(match.group(1))
    unite = match.group(2)
    if "minute" in unite:
        delta = timedelta(minutes=valeur)
    elif "heure" in unite:
        delta = timedelta(hours=valeur)
    elif "jour" in unite:
        delta = timedelta(days=valeur)
    else:
        return None, None, None
    maintenant = datetime.now()
    cible = maintenant + delta
    return cible.strftime("%Y-%m-%d"), cible.strftime("%H:%M"), match.span()


def _extraire_date_evenement(reste):
    """(date AAAA-MM-JJ, span (debut,fin)) reconnus dans `reste`, ou (None, None)."""
    for motif, delta in _DATE_RELATIVE_RE:
        m = motif.search(reste)
        if m:
            d = (datetime.now() + timedelta(days=delta)).strftime("%Y-%m-%d")
            return d, m.span()
    for i, jour in enumerate(_JOURS_SEMAINE):
        m = re.search(r"\b" + jour + r"\b", reste)
        if m:
            maintenant = datetime.now()
            delta = (i - maintenant.weekday()) % 7
            cible = maintenant + timedelta(days=delta)
            return cible.strftime("%Y-%m-%d"), m.span()
    m = _DATE_ISO_RE.search(reste)
    if m:
        annee, mois, jour = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(annee, mois, jour).strftime("%Y-%m-%d"), m.span()
        except ValueError:
            return None, None
    m = _DATE_EXPLICITE_RE.search(reste)
    if m:
        jour, mois = int(m.group(1)), int(m.group(2))
        annee_txt = m.group(3)
        annee = datetime.now().year
        if annee_txt:
            annee = int(annee_txt) if len(annee_txt) == 4 else 2000 + int(annee_txt)
        try:
            return datetime(annee, mois, jour).strftime("%Y-%m-%d"), m.span()
        except ValueError:
            return None, None

    # Repli tolerant aux fautes de frappe (ex. "dedmain" pour "demain",
    # faute reelle observee) : compare chaque mot de la phrase aux mots-cles
    # de date connus par similarite, plutot que par egalite stricte.
    mots_connus = list(_MOTS_DATE_RELATIVE_CONNUS) + _JOURS_SEMAINE
    for mot_trouve in re.finditer(r"[a-z']+", reste):
        mot = mot_trouve.group(0)
        if len(mot) < 5:
            continue  # trop court pour une comparaison floue fiable
        proches = difflib.get_close_matches(mot, mots_connus, n=1, cutoff=0.75)
        if not proches:
            continue
        trouve = proches[0]
        if trouve in _MOTS_DATE_RELATIVE_CONNUS:
            delta = _MOTS_DATE_RELATIVE_CONNUS[trouve]
            d = (datetime.now() + timedelta(days=delta)).strftime("%Y-%m-%d")
            return d, mot_trouve.span()
        i = _JOURS_SEMAINE.index(trouve)
        maintenant = datetime.now()
        delta = (i - maintenant.weekday()) % 7
        cible = maintenant + timedelta(days=delta)
        return cible.strftime("%Y-%m-%d"), mot_trouve.span()

    return None, None


def _extraire_heure_evenement(reste):
    """("HH:MM", span) reconnus dans `reste`, ou (None, None)."""
    m = _HEURE_RE.search(reste)
    if not m:
        return None, None
    heure = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if not (0 <= heure <= 23 and 0 <= minute <= 59):
        return None, None
    return "{:02d}:{:02d}".format(heure, minute), m.span()


def _etendre_article_precedent(texte, span):
    """Etend un span de date vers la gauche pour englober un article
    francais ("le "/"la "/"l'") qui le precede immediatement.

    Bug confirme : "cree un evenement le 2026-09-01 a 9h : ..." laissait un
    "Le" residuel en tete du titre, l'article n'etant pas retire avec la
    date (contrairement a "demain"/"lundi" ou aucun article ne precede).
    Cible uniquement l'article COLLE au debut de la date reconnue (pas un
    strip global du titre), pour ne jamais amputer un titre qui commencerait
    legitimement par "Le"/"La" sans rapport avec une date.
    """
    if not span:
        return span
    debut, fin = span
    m = re.search(r"(?:\bl[ae]\s+|\bl['’]\s*)$", texte[:debut])
    if m:
        return (m.start(), fin)
    return span


def _essai_ajout_rdv(text):
    """Reconnait 'ajoute un rendez-vous <titre> <date> a <heure>' ou
    'rappelle-moi de <titre> <date> a <heure>'.

    Renvoie :
      - un dict d'action "ajouter_evenement" complet si date ET heure sont
        reconnues sans ambiguite (execution garantie, sans LLM) ;
      - un dict d'action "demander_precision_evenement" si l'intention
        d'ajouter un rendez-vous est claire (declencheur reconnu) mais que
        la date ou l'heure n'a pas pu etre extraite (ex. faute de frappe
        trop importante) — GARANTIT qu'on ne laisse plus jamais le LLM
        halluciner une fausse confirmation pour cette action (observe
        reellement : confirmation orale credible recue, aucun evenement
        cree, a cause d'une simple faute de frappe sur "demain") ;
      - None si aucun declencheur d'ajout de rendez-vous n'est present du
        tout (l'appelant peut alors se rabattre sur le LLM pour autre chose).
    """
    norm = _sans_accents(text.strip().lower())
    if not norm:
        return None

    m_decl = _MOTS_DECLENCHEURS_EVENEMENT.search(norm)
    m_rappelle = None if m_decl else _RAPPELLE_MOI_RE.search(norm)
    if m_decl is None and m_rappelle is None:
        return None
    reste = norm[(m_decl or m_rappelle).end():]

    # 1. Tenter d'extraire une durée relative ("dans X minutes")
    date, heure, span_duree = _extraire_duree_relative(reste)
    if date is not None and heure is not None:
        # on a une date/heure absolue, on retire la durée du titre
        reste = reste[:span_duree[0]] + " " + reste[span_duree[1]:]
    else:
        # 2. Sinon, extraire date et heure classiques
        date, span_date = _extraire_date_evenement(reste)
        heure, span_heure = _extraire_heure_evenement(reste)

    if date is None or heure is None:
        return {"action": "demander_precision_evenement"}

    # Titre explicite ("sous le nom X", "intitule X"...) : prioritaire sur
    # le simple texte restant, plus fiable quand la phrase contient aussi
    # du bruit ("dedmain a 11h30de matin sous le nom test" -> "test", pas
    # tout le reste de la phrase).
    m_nom = re.search(
        r"(?:sous le nom|intitule|qui s['’]appelle|appele|nomme)\s+"
        r"(?:de\s+|d['’]\s*)?(.+)$",
        reste)
    if m_nom:
        titre = m_nom.group(1)
        # "intitule X" peut apparaitre AVANT la date/heure dans la phrase
        # ("... intitule reunion de crise demain a 9h") : on les retire donc
        # aussi du texte capture, pas seulement du reste global.
        _, span_date_t = _extraire_date_evenement(titre)
        span_date_t = _etendre_article_precedent(titre, span_date_t)
        _, span_heure_t = _extraire_heure_evenement(titre)
        for debut, fin in sorted(
                [s for s in (span_date_t, span_heure_t) if s], reverse=True):
            titre = titre[:debut] + " " + titre[fin:]
    else:
        # Sinon : retire les deux portions reconnues (la plus a droite
        # d'abord, pour ne pas decaler les indices de l'autre) — ce qui
        # reste est le titre.
        titre = reste
        # utiliser les spans de date/heure extraits (si non None)
        spans = []
        if 'span_date' in locals() and span_date:
            spans.append(_etendre_article_precedent(titre, span_date))
        if 'span_heure' in locals() and span_heure:
            spans.append(span_heure)
        # span_duree n'est PAS rajoute ici : quand _extraire_duree_relative a
        # reussi (ligne ~457), `reste` a deja ete reecrit pour retirer ce
        # segment. Le reappliquer une seconde fois utilisait des indices
        # perimes (calcules sur l'ancien `reste`, plus long) et decoupait au
        # mauvais endroit -> bug confirme : "rappelle-moi dans 30 minutes de
        # sortir les poubelles" donnait le titre "Poubelles" au lieu de
        # "Sortir les poubelles".
        for debut, fin in sorted([s for s in spans if s], reverse=True):
            titre = titre[:debut] + " " + titre[fin:]
    # Connecteur residuel ("de "/"d'"/"pour ") : ni _RAPPELLE_MOI_RE ni le
    # retrait des spans date/heure ne consomment ces mots de liaison quand
    # ils precedent la date plutot que de la suivre immediatement — ex.
    # "programme un rappel POUR lundi 10h : appeler le medecin" laissait
    # "Pour : appeler le medecin" comme titre (bug confirme) une fois la
    # date/heure retirees ; meme cause que "de" pour un delai relatif place
    # avant le titre ("rappelle-moi dans 30 minutes DE sortir...").
    titre = re.sub(r"^\s*(?:de\s+|d['’]\s*|pour\s+)", "", titre)
    titre = re.sub(r"\s+", " ", titre).strip(" .,:;-'’")
    if not titre:
        return {"action": "demander_precision_evenement"}

    return {
        "action": "ajouter_evenement",
        "titre": titre[:1].upper() + titre[1:],
        "date": date,
        "heure": heure,
        "description": "",
        "rappel": 10,
    }


def try_fast_path(text):
    """Reconnait une commande frequente sans passer par le LLM.

    Renvoie un dict d'action (meme forme que extract_json) si reconnue, ou
    None sinon — dans ce cas l'appelant doit se rabattre sur le LLM.
    """
    if not text:
        return None

    ajout_rdv = _essai_ajout_rdv(text)
    if ajout_rdv is not None:
        return ajout_rdv

    brut = _sans_accents(text.strip().lower())

    # "mode X" est ambigu entre theme d'interface et mode de la carte :
    # on tranche selon le mot capture.
    m = re.search(r"\bmode ([a-z]+)\b", brut)
    if m:
        mot = m.group(1)
        if mot in _MODE_THEME_MOTS:
            return {"action": "changer_theme", "theme": _MODE_THEME_MOTS[mot]}
        if mot in _ALIAS_MODE_CARTE:
            return {"action": "regler_mode_carte", "mode": mot}

    # "ouvre/lance/va dans <app>" — reconnait meme avec du texte apres le nom
    # (ex. "ouvre la carte s'il te plait" -> on ne garde que le 1er mot utile).
    # "les " doit etre teste avant "l['] " : un "." joker y matcherait aussi
    # "le" (les deux premieres lettres de "les"), ce qui cassait la capture.
    m = re.search(r"\b(?:ouvre|ouvrir|lance|va dans|va sur)\s+"
                  r"(?:les |la |le |mes |tes |vos |l['’ ])?([a-z]+)", brut)
    if m:
        app_id = _APP_ALIASES.get(m.group(1))
        if app_id:
            return {"action": "ouvrir_app", "app": app_id}

    # "cherche/recherche/trouve X sur internet/le web/google" — phrasing
    # sans ambiguite (le qualificatif final la distingue d'une simple
    # discussion), donc sure a court-circuiter le LLM. Les deux ordres sont
    # geres (meme bug que "sur navigateur" corrige plus bas : "cherche sur
    # internet X" place le qualificatif AVANT l'objet, pas apres — sans ce
    # premier motif, "sur internet" se retrouvait avale dans la requete).
    m = re.search(
        r"(?:cherche[rsz]?|recherche[rsz]?|trouve[rsz]?(?:.moi)?)\s+"
        r"sur (?:internet|le web|google|duckduckgo)\s+(.+)$", brut)
    if m:
        requete = m.group(1).strip()
        if requete:
            return {"action": "rechercher_web", "requete": requete}
    m = re.search(
        r"(?:cherche|recherche|trouve(?:.moi)?)\s+(.+?)\s+"
        r"sur (?:internet|le web|google|duckduckgo)\b", brut)
    if m:
        return {"action": "rechercher_web", "requete": m.group(1).strip()}

    # "cherche/ouvre X sur/dans/avec le navigateur" — audit (bug reel
    # observe) : sans cette regle, "sur navigateur" se retrouvait avale tel
    # quel DANS la requete de recherche (rechercher_web echouait toujours,
    # "sur navigateur" n'ayant aucun sens comme terme de recherche). Ici,
    # l'intention est explicitement d'ouvrir un navigateur, pas de chercher
    # localement — routee vers ouvrir_navigateur, jamais vers rechercher_web.
    # Les deux ordres sont reconnus ("cherche X sur navigateur" ET "cherche
    # sur navigateur X" — ce second ordre est celui reellement observe).
    m = re.search(
        r"\b(?:cherche[rsz]?|recherche[rsz]?|trouve[rsz]?(?:.moi)?)\s+"
        r"(?:sur|dans|avec)\s+(?:le\s+|un\s+)?navigateur\s+(.*)$", brut)
    if m:
        requete = m.group(1).strip()
        return ({"action": "ouvrir_navigateur", "requete": requete} if requete
                else {"action": "ouvrir_navigateur"})
    m = re.search(
        r"\b(?:cherche[rsz]?|recherche[rsz]?|trouve[rsz]?(?:.moi)?)\s+"
        r"(.*?)\s*(?:sur|dans|avec)\s+(?:le\s+|un\s+)?navigateur\b", brut)
    if m:
        requete = m.group(1).strip()
        return ({"action": "ouvrir_navigateur", "requete": requete} if requete
                else {"action": "ouvrir_navigateur"})

    # "ouvre/lance le navigateur" (sans requete precise) — "navigateur"
    # n'est volontairement pas un alias d'app (_APP_ALIASES) car ce n'est
    # pas une application NOVA : sans cette regle dediee, la commande
    # tombait sur le LLM qui repondait par une question au lieu d'agir
    # (bug reel observe : "ouvre navigateur" -> LLM demande "quelle
    # recherche voulez-vous faire ?" au lieu d'ouvrir quoi que ce soit).
    m = re.search(r"\b(?:ouvre|ouvrir|lance|lancer)\s+(?:le\s+|un\s+)?navigateur\b",
                  brut)
    if m:
        return {"action": "ouvrir_navigateur"}

    for motif, fabrique in _FAST_PATH_RULES:
        trouve = motif.search(brut)
        if trouve:
            return fabrique(trouve)

    # Repli : "(peux-tu) cherche/chercher/recherche/rechercher/trouve(r) X"
    # SANS qualificatif ("sur internet"), qui n'a matché aucune regle nommee
    # ci-dessus (fichiers, suggestions, navigation...). Pas d'ancrage en debut
    # de phrase : accepte les preambules courants ("est-ce que tu peux...",
    # "j'aimerais que tu..."). Cahier des charges (BUG 1) : "recherche X" doit
    # toujours afficher un resultat dans le chat, jamais ouvrir de navigateur
    # ni dependre du LLM (peu fiable pour produire le JSON d'action) pour ce
    # cas frequent.
    m = re.search(
        r"\b(?:cherche[rsz]?|recherche[rsz]?|trouve[rsz]?(?:.moi)?)\b\s+(.+)$",
        brut)
    if m:
        requete = m.group(1).strip()
        if requete:
            return {"action": "rechercher_web", "requete": requete}

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Exécution des actions
# ─────────────────────────────────────────────────────────────────────────────
def execute_action(data, app=None):
    """Exécute la commande JSON. Renvoie une phrase de confirmation (str),
    None si l'action est inconnue, ou un message d'échec honnête si le
    handler a leve une exception inattendue (durcissement audit : un JSON
    malforme ou un argument innattendu du LLM ne doit jamais faire planter
    la chaine assistant/reponse vocale — l'exception est loggee, pas propagee).
    """
    if not isinstance(data, dict):
        print("[actions] commande invalide (pas un objet) :", data)
        return None
    try:
        return _dispatch_action(data, app)
    except Exception as error:
        print("[actions] erreur inattendue sur l'action « {} » : {}".format(
            data.get("action"), error))
        return "Je n'ai pas pu terminer cette action."


def _dispatch_action(data, app=None):
    action = data.get("action")

    if action:
        try:
            from nova import memory_store
            memory_store.note_usage("action", action)
        except Exception as error:
            print("[actions] compteur de frequence :", error)

    if action == "ajouter_evenement":
        return _add_event(data, app)
    if action == "demander_precision_evenement":
        return _demander_precision_evenement()
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
    if action == "regler_mode_carte":
        return _set_map_mode(data, app)
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
    if action == "aide":
        return _aide()
    if action == "rechercher_web":
        return _web_search(data)
    if action == "ouvrir_navigateur":
        return _open_browser(data)
    if action == "fichiers_lister":
        return _fichiers_lister(data, app)
    if action == "fichiers_creer_dossier":
        return _fichiers_creer_dossier(data, app)
    if action == "fichiers_supprimer":
        return _fichiers_supprimer(data, app)
    if action == "changer_langue":
        return _set_language(data)
    if action == "suggestions":
        return _suggestions(app)
    # Nouvelle action : mode économie d'énergie
    if action == "mode_economie":
        return _set_power_saving(data)
    return None


def _demander_precision_evenement():
    """Reponse deterministe quand une intention d'ajout de rendez-vous est
    detectee mais que la date ou l'heure reste ambigue (chemin rapide,
    assistant_actions._essai_ajout_rdv). Ne passe jamais par le LLM pour ce
    cas : garantit qu'aucune fausse confirmation n'est produite."""
    return ("Je n'ai pas compris la date ou l'heure du rendez-vous. Pouvez-vous "
            "repeter avec une date et une heure precises, par exemple "
            "« demain a 15h » ?")


def _add_event(data, app):
    titre = (data.get("titre") or "Événement").strip()
    date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    heure = data.get("heure") or "12:00"
    description = (data.get("description") or "").strip()
    rappel = _int_borne(data.get("rappel"), defaut=10, minimum=0, maximum=1440)
    try:
        from apps.calendar import storage
        storage.add_event(title=titre, date=date, time=heure,
                          description=description, reminder=rappel)
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
            date_fr = d.strftime("%d/%m")
        except ValueError:
            date_fr = date
        if rappel:
            return "C'est noté : « {} » le {} à {}, rappel {} min avant.".format(
                titre, date_fr, heure, rappel)
        return "C'est noté : « {} » le {} à {}.".format(titre, date_fr, heure)
    except Exception as error:
        # L'erreur reelle n'apparaissait qu'en print(), invisible sur un
        # wearable sans terminal attache — on la rend visible dans le chat.
        print("[actions] ajout événement impossible :", error)
        return "Je n'ai pas réussi à enregistrer l'événement ({}).".format(error)


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
        return "Je n'ai pas pu consulter l'agenda ({}).".format(error)


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
        return "Je n'ai pas pu supprimer les événements ({}).".format(error)


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


def _aide():
    """Liste ce que NOVA sait faire — utile quand l'utilisateur ne sait pas
    quoi demander, ou quand une commande n'a pas ete comprise."""
    return (
        "Je peux : gerer votre agenda (ajouter/voir/supprimer un "
        "rendez-vous), calculer un itineraire et changer le mode de la "
        "carte (normal, marche, conduite), ouvrir une application, "
        "regler le volume, la luminosite, le WiFi, le Bluetooth ou le "
        "theme, lire les capteurs, controler la radio, donner l'heure "
        "ou la batterie, faire vibrer l'appareil, prendre une photo, "
        "gerer vos fichiers (lister, creer un dossier, supprimer avec "
        "confirmation), chercher une information sur internet si je suis "
        "connecte, changer de langue (francais, anglais, arabe), ou vous "
        "faire des suggestions. Dites par exemple : « ouvre l'agenda », "
        "« mode conduite », « mes fichiers », « cherche qui est Ibn "
        "Khaldoun », « des suggestions », ou « rappelle-moi demain a huit "
        "heures d'appeler quelqu'un »."
    )


# ═════════════════════════════════════════════════════════════════════════
# RECHERCHE WEB (capacite "JARVIS" — necessite une connexion internet)
# ═════════════════════════════════════════════════════════════════════════
def _web_search(data):
    """Cherche une information reelle sur le web et la lit a voix haute.

    Contrairement au reste de NOVA, ceci depend du reseau : echoue de
    facon honnete (message clair) si hors ligne, plutot que d'inventer
    une reponse ou de planter.
    """
    requete = (data.get("requete") or "").strip()
    if not requete:
        return "Que voulez-vous que je cherche ?"
    from nova import web_search
    if not web_search.is_online():
        return "Pas de connexion internet pour faire une recherche."
    resultats = web_search.search(requete)
    reponse = web_search.format_for_speech(resultats, requete)
    if reponse:
        return reponse
    # Repli (accord utilisateur explicite) : DuckDuckGo (reponse instantanee)
    # et Wikipedia ne couvrent que le factuel/encyclopedique — rien pour un
    # commerce local, un produit, un prix... Plutot que d'echouer poliment
    # sans jamais donner d'information reelle ("Je n'ai rien trouve pour..."),
    # on ouvre un vrai navigateur avec un vrai moteur de recherche sur la
    # meme requete. Different du bug original (recherche_web ouvrait TOUJOURS
    # un navigateur sans jamais essayer localement d'abord) : ici la
    # recherche locale est toujours tentee en premier, le navigateur n'est
    # qu'un dernier recours si elle echoue vraiment.
    return _open_browser({"requete": requete})


def _open_browser(data):
    """Ouvre le navigateur (ex. pour approfondir une recherche a l'ecran)."""
    requete = (data.get("requete") or "").strip()
    import urllib.parse
    import webbrowser
    url = ("https://duckduckgo.com/?" + urllib.parse.urlencode({"q": requete})
           if requete else "https://duckduckgo.com/")
    try:
        ouvert = webbrowser.open(url)
    except Exception as error:
        print("[actions] ouverture navigateur impossible :", error)
        ouvert = False
    if not ouvert:
        return "Je n'ai pas pu ouvrir de navigateur sur cet appareil."
    return ("J'ouvre la recherche pour « {} ».".format(requete) if requete
            else "J'ouvre le navigateur.")


# ═════════════════════════════════════════════════════════════════════════
# FICHIERS
# ═════════════════════════════════════════════════════════════════════════
def _fichiers_ecran(app):
    """Renvoie l'ecran de l'app Fichiers, meme si elle n'est pas affichee."""
    manager = _screens(app)
    if manager is None:
        return None
    try:
        return manager.get_screen("files")
    except Exception:
        return None


def _fichiers_afficher(app):
    manager = _screens(app)
    if manager is not None:
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: setattr(manager, "current", "files"), 0)


def _fichiers_lister(data, app):
    ecran = _fichiers_ecran(app)
    if ecran is None:
        return "Impossible d'acceder aux fichiers."

    nom_dossier = (data.get("dossier") or "").strip().lower()
    if nom_dossier and nom_dossier not in ("racine", "accueil", "debut"):
        cible = None
        try:
            for enfant in ecran.dossier_courant.iterdir():
                if enfant.is_dir() and enfant.name.lower() == nom_dossier:
                    cible = enfant
                    break
        except Exception:
            cible = None
        if cible is None:
            return "Je ne trouve pas de dossier « {} » ici.".format(data.get("dossier"))
        ecran.ouvrir(cible)

    try:
        entrees = sorted(ecran.dossier_courant.iterdir(),
                         key=lambda p: (not p.is_dir(), p.name.lower()))
    except Exception as error:
        print("[actions] lecture fichiers impossible :", error)
        return "Je n'ai pas pu lire ce dossier."

    _fichiers_afficher(app)
    if not entrees:
        return "Ce dossier est vide."
    noms = [e.name for e in entrees[:8]]
    reste = len(entrees) - len(noms)
    phrase = "Il y a {} element{} : {}".format(
        len(entrees), "s" if len(entrees) > 1 else "", ", ".join(noms))
    if reste > 0:
        phrase += ", et {} de plus".format(reste)
    return phrase + "."


def _fichiers_creer_dossier(data, app):
    nom = (data.get("nom") or "").strip()
    if not nom:
        return "Quel nom voulez-vous donner au dossier ?"
    ecran = _fichiers_ecran(app)
    if ecran is None:
        return "Impossible d'acceder aux fichiers."
    from kivy.clock import Clock
    Clock.schedule_once(lambda dt: ecran.creer_dossier(nom), 0)
    _fichiers_afficher(app)
    return "Je cree le dossier « {} ».".format(nom)


def _fichiers_supprimer(data, app):
    """Supprime un fichier/dossier PAR SON NOM — mais ne le fait jamais en
    silence : ouvre la meme boite de confirmation que dans l'interface,
    l'utilisateur doit toujours valider a l'ecran avant que rien ne soit
    reellement efface (commande vocale mal comprise = pas de perte de
    donnees)."""
    nom = (data.get("nom") or "").strip()
    if not nom:
        return "Quel fichier ou dossier voulez-vous supprimer ?"
    ecran = _fichiers_ecran(app)
    if ecran is None:
        return "Impossible d'acceder aux fichiers."
    cible = None
    try:
        for enfant in ecran.dossier_courant.iterdir():
            if enfant.name.lower() == nom.lower():
                cible = enfant
                break
    except Exception:
        cible = None
    if cible is None:
        return "Je ne trouve pas « {} » dans ce dossier.".format(nom)

    from kivy.clock import Clock
    _fichiers_afficher(app)
    Clock.schedule_once(lambda dt: ecran._confirmer_suppression(cible), 0)
    return "Confirmez la suppression de « {} » a l'ecran.".format(nom)


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
    try:
        from nova import memory_store
        memory_store.note_usage("destination", destination)
    except Exception as error:
        print("[actions] compteur destinations :", error)
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


_ALIAS_MODE_CARTE = {
    "normal": "normal", "standard": "normal", "classique": "normal",
    "marche": "walk", "pieton": "walk", "piéton": "walk", "a pied": "walk",
    "à pied": "walk", "walk": "walk",
    "conduite": "drive", "voiture": "drive", "route": "drive", "drive": "drive",
}


def _set_map_mode(data, app):
    """Change le mode d'affichage/navigation de l'app Maps (Phase 6 : mode
    normal vs mode personnalise marche/conduite)."""
    demande = (data.get("mode") or "").strip().lower()
    mode = _ALIAS_MODE_CARTE.get(demande)
    if not mode:
        return "Mode inconnu. Dites normal, marche ou conduite."
    manager = _screens(app)
    if manager is None:
        return "Impossible de changer le mode de la carte."
    from kivy.clock import Clock

    def appliquer(_dt):
        manager.current = "maps"
        ecran = manager.get_screen("maps")
        if hasattr(ecran, "_set_mode"):
            ecran._set_mode(mode)
    Clock.schedule_once(appliquer, 0)
    libelles = {"normal": "normal", "walk": "marche", "drive": "conduite"}
    return "Mode carte : {}.".format(libelles[mode])


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


def _int_borne(valeur, defaut, minimum, maximum):
    """Coerce/borne un argument numerique venant du LLM (jamais garanti valide :
    le modele peut renvoyer une chaine, un flottant, ou une valeur aberrante)."""
    try:
        n = int(valeur)
    except (TypeError, ValueError):
        return defaut
    return max(minimum, min(maximum, n))


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


_ALIAS_LANGUE = {
    "francais": "fr", "français": "fr", "french": "fr", "fr": "fr",
    "anglais": "en", "english": "en", "en": "en",
    "arabe": "ar", "arabic": "ar", "ar": "ar", "عربي": "ar", "العربية": "ar",
}

_CONFIRMATION_LANGUE = {
    "fr": "Langue changée pour le français.",
    "en": "Language switched to English.",
    "ar": "تم تغيير اللغة إلى العربية.",
}


def _set_language(data):
    """Change la langue de reponse (prompt systeme LLM + Whisper STT).

    Limite assumee et documentee : une seule voix Piper FR est installee
    (fr_FR-siwis-medium.onnx) ; en anglais/arabe, NOVA repond par ecrit sans
    forcer une synthese vocale dans la mauvaise langue plutot que de mentir
    sur une capacite vocale qui n'existe pas encore.
    """
    demande = (data.get("langue") or "").strip().lower()
    langue = _ALIAS_LANGUE.get(demande)
    if not langue:
        return "Langue inconnue. Dites français, anglais ou arabe."
    try:
        _config().set("language", langue)
        return _CONFIRMATION_LANGUE[langue]
    except Exception as error:
        print("[actions] langue :", error)
        return "Je n'ai pas pu changer la langue."


def _suggestions(app):
    """Suggestions proactives : prochain evenement + destination la plus
    recherchee. Base sur des comptes SQL simples (memory_store.top_usage,
    storage.next_event_label) — statistique, pas de l'apprentissage
    automatique (cf. JARVIS_INTEGRATION_PLAN.md pour la distinction)."""
    parties = []

    try:
        from apps.calendar import storage
        label = storage.next_event_label()
        if label and "aucun" not in label.lower():
            parties.append("Votre prochain événement : {}.".format(label))
    except Exception as error:
        print("[actions] suggestions agenda :", error)

    try:
        from nova import memory_store
        top = memory_store.top_usage("destination", limit=1)
        if top and top[0]["count"] >= 2:
            parties.append(
                "Vous recherchez souvent « {} » — voulez-vous que je calcule "
                "l'itinéraire ?".format(top[0]["value"]))
    except Exception as error:
        print("[actions] suggestions destination :", error)

    if not parties:
        return "Je n'ai pas encore assez d'historique pour vous faire des suggestions."
    return " ".join(parties)


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
# MODE ÉCONOMIE D'ÉNERGIE (nouveau)
# ═════════════════════════════════════════════════════════════════════════
def _set_power_saving(data):
    """Active ou désactive le mode économie d'énergie.

    Réduit la luminosité, désactive les animations Kivy, et ajuste d'autres
    paramètres pour économiser la batterie.
    """
    actif = _bool_actif(data, defaut=True)
    try:
        cfg = _config()
        cfg.set("power_saving", actif)
        # Appliquer les changements au niveau de l'interface
        from kivy.clock import Clock
        if actif:
            # Réduire la luminosité à 30% si elle est > 50
            bright = cfg.get("audio", {}).get("brightness", 100)
            if bright > 50:
                _set_brightness({"valeur": 30})
            # Désactiver les animations (via un flag global)
            try:
                from kivy.config import Config
                Config.set('kivy', 'animation_duration', '0.0')
            except Exception:
                pass
            # Désactiver l'écran de veille trop fréquent
            # (déjà géré par le timeout)
            return "Mode économie d'énergie activé. Luminosité réduite, animations désactivées."
        else:
            # Restaurer la luminosité à 80%
            _set_brightness({"valeur": 80})
            try:
                from kivy.config import Config
                Config.set('kivy', 'animation_duration', '0.2')
            except Exception:
                pass
            return "Mode économie d'énergie désactivé. Paramètres normaux restaurés."
    except Exception as error:
        print("[actions] mode economie :", error)
        return "Je n'ai pas pu changer le mode économie."


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
