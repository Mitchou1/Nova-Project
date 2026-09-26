#!/usr/bin/env python3
"""Recherche web pour NOVA : donner la RÉPONSE dans le chat, avec sa source.

Contrairement au reste de NOVA (conçu pour marcher hors ligne), ceci a
BESOIN d'internet. Hors ligne, on le dit clairement, sans jamais inventer.

Cascade de sources, de la plus fiable à la plus fragile :
  0. Météo -> Open-Meteo (API sans clé) : une question météo n'a pas sa
     réponse dans une encyclopédie (avant : « météo à Tunis » renvoyait
     l'article Wikipédia sur la ville de Tunis).
  1. DuckDuckGo Instant Answer (API JSON) : réponses factuelles directes.
  2. Wikipédia (FR puis EN) : résultats CLASSÉS par pertinence. Avant, le
     1er résultat était pris tel quel : « qui a gagné la coupe du monde
     2022 » donnait l'article sur la Coupe du monde 2026.
  3. Scraping léger d'un moteur (DuckDuckGo HTML puis Bing) : extraits de
     pages web, pour ce qui n'est pas encyclopédique (prix, actualité...).
     Fragile : ces moteurs renvoient parfois une page anti-robot. C'est
     détecté, et le moteur est mis en pause 15 min au lieu d'insister.

Pour une question « d'actualité » (prix, score, aujourd'hui...), le
scraping passe AVANT Wikipédia : l'encyclopédie donnerait une définition
(« prix du bitcoin » -> « Le Bitcoin est une cryptomonnaie... »).

La réponse est une synthèse de 2 à 4 phrases, nettoyée (phonétique,
parenthèses en écriture non latine...), avec la source citée.
"""

import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "NOVA-Wearable/1.0 (personal project; contact: mitchou425@gmail.com)"
# Les moteurs de recherche servent une page anti-robot à un User-Agent
# inconnu (cause de l'abandon du scraping dans l'ancienne version) : pour
# eux seulement, on se présente comme un navigateur ordinaire.
BROWSER_UA = "Mozilla/5.0 (X11; Linux aarch64; rv:128.0) Gecko/20100101 Firefox/128.0"
TIMEOUT = 6
PAUSE_BLOCAGE = 15 * 60          # secondes de pause d'un moteur qui bloque
MAX_CARACTERES = 450             # longueur visée d'une réponse (2 à 4 phrases)

# moteur -> instant jusqu'auquel on ne l'interroge plus (page anti-robot)
_moteurs_bloques = {}


# ═════════════════════════════════════════════════════════════════════════
# Réseau
# ═════════════════════════════════════════════════════════════════════════
def _get(url, ua=USER_AGENT, data=None, timeout=TIMEOUT):
    """Renvoie (code HTTP, texte). Lève une exception si pas de réponse."""
    headers = {"User-Agent": ua, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5"}
    corps = urllib.parse.urlencode(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=corps, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def _get_json(url):
    return json.loads(_get(url)[1])


def is_online(timeout=3):
    """Y a-t-il une connexion internet ?

    Une réponse HTTP d'erreur (403, 429...) prouve quand même qu'on est en
    ligne : avant, un simple refus de DuckDuckGo faisait croire à NOVA
    qu'il était hors ligne. Plusieurs hôtes sont essayés.
    """
    for url in ("https://fr.wikipedia.org/", "https://duckduckgo.com/",
                "https://api.open-meteo.com/"):
        try:
            _get(url, timeout=timeout)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            continue
    return False


# ═════════════════════════════════════════════════════════════════════════
# Analyse de la question
# ═════════════════════════════════════════════════════════════════════════
def _norm(texte):
    nfkd = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_MOTS_VIDES = set("""
a au aux avec c ce ces cet cette comment combien d dans de des du elle en est et
etait il ils j je l la le les leur lui ma me mes moi mon ne on ou par pas pour
qu quand que quel quelle quelles quels qui quoi sa se ses son sont sur t ta te tes
toi ton tu un une vos votre vous y cherche chercher recherche rechercher trouve
trouver internet web google dis donne moi sais savoir connais
""".split())

_ACTUALITE_RE = re.compile(
    r"\b(prix|cours|tarif|combien coute|cotation|score|resultats? du match|"
    r"actualites?|actus?|news|aujourd.?hui|en ce moment|maintenant|actuel(?:le)?s?|"
    r"derniers?|dernieres?|recents?|recentes?|taux de change|bourse|en direct)\b")

_METEO_RE = re.compile(
    r"\b(meteo|quel temps|temps qu.il (?:fait|fera)|va.t.il pleuvoir|pleuvoir|"
    r"previsions?|temperature (?:a|au|en|de|pour))\b")


def _singulier(mot):
    return mot[:-1] if len(mot) > 3 and mot.endswith(("s", "x")) and not mot.isdigit() else mot


def _mots(texte):
    """Ensemble des mots d'un texte, sans accents, au singulier approximatif
    (« champions » doit correspondre à « champion »)."""
    return {_singulier(m) for m in re.findall(r"[a-z0-9]+", _norm(texte))}


def mots_cles(question):
    """Mots porteurs de sens de la question (sans mots vides ni accents)."""
    return [_singulier(m) for m in re.findall(r"[a-z0-9]+", _norm(question))
            if m not in _MOTS_VIDES and len(m) > 1]


# Mots qui décrivent la RÉPONSE attendue, pas le sujet : ils servent à
# choisir la bonne phrase mais brouillent la recherche Wikipédia (« qui a
# gagné la coupe du monde 2022 » ne trouvait pas l'article de 2022, alors
# que « coupe monde 2022 » le trouve en premier).
_MOTS_REPONSE = {"gagne", "gagner", "remporte", "vainqueur", "invente", "inventeur",
                 "fonde", "fondateur", "cree", "createur", "age", "fonctionne",
                 "signifie", "veut", "dire", "definition"}


def mots_recherche(question):
    """Termes à envoyer au moteur de Wikipédia (sujet de la question seul)."""
    mots = [m for m in re.findall(r"[a-z0-9]+", _norm(question))
            if m not in _MOTS_VIDES and m not in _MOTS_REPONSE and len(m) > 1]
    return " ".join(mots) or question


def est_actualite(question):
    return bool(_ACTUALITE_RE.search(_norm(question)))


def est_meteo(question):
    return bool(_METEO_RE.search(_norm(question)))


# ═════════════════════════════════════════════════════════════════════════
# Synthèse : 2 à 4 phrases propres
# ═════════════════════════════════════════════════════════════════════════
def _nettoyer(texte):
    """Retire ce qui gêne la lecture et la synthèse vocale : transcriptions
    phonétiques « [tuʁɛfɛl] », parenthèses en écriture non latine (nom
    complet en arabe...) ou trop longues, espaces en double."""
    texte = html.unescape(texte or "").replace("\xa0", " ")
    texte = re.sub(r"\s*\[[^\]]*\]", "", texte)
    # Écritures non latines (arabe, hébreu, cyrillique, grec...) : illisibles
    # par la voix française, et souvent dans des parenthèses mal fermées par
    # Wikipédia lui-même (cas réel : Ibn Khaldoun).
    texte = re.sub(r"[\u0370-\u03FF\u0400-\u04FF\u0590-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+"
                   r"(?:[\s,'-]+[\u0370-\u03FF\u0400-\u04FF\u0590-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+)*",
                   "", texte)
    # Libellés devenus vides : « en arabe : ; nom complet : , »
    for _ in range(3):
        texte = re.sub(r"(?<=[(;,])\s*[\w' -]{1,25}\s*:\s*(?=[;,)])", "", texte)
        texte = re.sub(r"\(\s*[;,]\s*", "(", texte)
        texte = re.sub(r"\s*[;,]\s*(?=[;,)])", "", texte)
    texte = re.sub(r"\(\s*\)", "", texte)
    # « (prononcé [paʁi]) » devient « (prononcé) » une fois la phonétique ôtée
    texte = re.sub(r"\s*\(\s*(?:prononcé|prononciation|écouter)\s*:?\s*\)", "", texte,
                   flags=re.IGNORECASE)

    def parenthese(m):
        contenu = m.group(1)
        non_latin = any(ord(c) > 0x24F and c.isalpha() for c in contenu)
        if non_latin or len(contenu) > 50 or not contenu.strip():
            return ""               # digression trop longue pour une réponse courte
        return " ⟨" + contenu + "⟩"   # gardée, mise de côté le temps des autres passes
    # Des parenthèses les plus internes vers l'extérieur (imbrication)
    for _ in range(3):
        texte = re.sub(r"\s*\(([^()]*)\)", parenthese, texte)
    # Parenthèse ouverte jamais refermée : « Ibn Khaldoun (né le ... au Caire,
    # est un historien » -> « Ibn Khaldoun, né le ... » se lit naturellement.
    while texte.count("(") > texte.count(")"):
        i = texte.rfind("(")
        texte = texte[:i].rstrip() + ", " + texte[i + 1:].lstrip()
    texte = re.sub(r"(?<=[(;,])\s*[\w' -]{1,25}\s*:\s*(?=[;,)])", "", texte)
    texte = texte.replace("⟨", "(").replace("⟩", ")")
    texte = re.sub(r"\s+([,.;:])", r"\1", texte)
    texte = re.sub(r",\s*,", ",", texte)
    texte = re.sub(r"\s+", " ", texte).strip().strip(" …")
    if texte and not texte.endswith((".", "!", "?")):
        texte += "."
    return texte


# Abréviations à ne pas prendre pour une fin de phrase
# (« J.-C. » n'y figure pas : suivi d'une majuscule, il termine la phrase.)
_ABREVIATIONS = ("av.", "apr.", "env.", "M.", "Mme.", "Dr.", "St.",
                 "etc.", "cf.", "p.", "vol.", "c.-à-d.")


def _phrases(texte):
    morceaux = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Ý0-9«\"])", texte)
    phrases = []
    for m in morceaux:
        if phrases and (phrases[-1].endswith(_ABREVIATIONS)
                        or re.search(r"(?:^|\s)[A-Z]\.$", phrases[-1])):
            phrases[-1] += " " + m      # « J.-C. Il ... » : même phrase
        else:
            phrases.append(m)
    return [p.strip() for p in phrases if p.strip()]


# Mots de la réponse attendue pour certains mots de la question : « population
# de Sfax » -> la phrase utile parle d'« habitants », pas de « population ».
_SYNONYMES = {
    "population": {"habitants", "habitant"}, "habitants": {"population"},
    "hauteur": {"metres", "m", "haute", "haut"}, "taille": {"metres", "cm", "m"},
    "gagne": {"remporte", "vainqueur", "champion", "championne", "victoire"},
    "vainqueur": {"remporte", "gagne", "champion"},
    "age": {"ans", "ne", "nee"}, "ne": {"naissance"}, "mort": {"deces", "meurt"},
    "superficie": {"km2", "km", "kilometres"}, "distance": {"km", "kilometres"},
    "capitale": {"capitale"}, "fondateur": {"fonde", "fondee", "cree"},
    "invente": {"inventeur", "invention"}, "prix": {"euros", "dollars", "eur", "usd"},
}


def _cles_etendues(question):
    cles = set(mots_cles(question))
    for c in list(cles):
        cles |= {_singulier(x) for x in _SYNONYMES.get(c, set())}
    return cles


def synthese(texte, question, max_phrases=4, max_car=MAX_CARACTERES):
    """Garde la 1re phrase (souvent la définition) puis les phrases qui
    parlent le plus de la question, dans l'ordre du texte, dans la limite
    de max_phrases et d'environ max_car caractères."""
    phrases = _phrases(_nettoyer(texte))
    if not phrases:
        return ""
    cles = _cles_etendues(question)

    def score(p):
        mots = _mots(p)
        return len(cles & mots) + sum(1 for c in cles if c.isdigit() and c in mots)

    retenues = {0}
    total = len(phrases[0])
    candidates = sorted(range(1, len(phrases)), key=lambda i: (-score(phrases[i]), i))
    for i in candidates:
        if len(retenues) >= max_phrases:
            break
        # au moins 2 phrases si possible ; au-delà, seulement si pertinentes
        if len(retenues) >= 2 and score(phrases[i]) == 0:
            break
        if total + len(phrases[i]) > max_car and total > 120:
            continue
        retenues.add(i)
        total += len(phrases[i])
    return " ".join(phrases[i] for i in sorted(retenues))


def _pertinent(texte, question):
    """Le texte parle-t-il vraiment de la question ? Les nombres de la
    question (années, quantités) doivent y figurer : c'est ce qui distingue
    la Coupe du monde 2022 de celle de 2026."""
    cles = mots_cles(question)
    if not cles:
        return True
    mots = _mots(texte)
    if any(n not in mots for n in cles if n.isdigit()):
        return False
    return any(c in mots for c in cles if not c.isdigit())


def _reponse(texte, source, url=""):
    return {"ok": True, "texte": texte, "source": source, "url": url}


# ═════════════════════════════════════════════════════════════════════════
# Source 0 : météo (Open-Meteo)
# ═════════════════════════════════════════════════════════════════════════
_WMO = {
    0: "ciel dégagé", 1: "ciel plutôt dégagé", 2: "partiellement nuageux",
    3: "couvert", 45: "brouillard", 48: "brouillard givrant",
    51: "bruine légère", 53: "bruine", 55: "bruine forte",
    61: "pluie faible", 63: "pluie", 65: "forte pluie",
    71: "neige faible", 73: "neige", 75: "forte neige",
    80: "averses", 81: "averses", 82: "violentes averses",
    95: "orages", 96: "orages avec grêle", 99: "orages avec grêle",
}
# Position par défaut tant que le GPS n'est pas branché (même que l'app Maps)
_POSITION_DEFAUT = ("Tunis", 36.8065, 10.1815)


def ville_meteo(question):
    """« météo à Sousse demain » -> « Sousse » ; None si pas de ville."""
    q = re.sub(r"\s+(?:aujourd'hui|aujourd’hui|demain|ce soir|cette semaine|maintenant)\s*\??$",
               "", question.strip(), flags=re.IGNORECASE)
    m = re.search(r"\b(?:à|a|au|en|pour|sur)\s+([A-Za-zÀ-ÿ' -]+?)\s*\??$", q, re.IGNORECASE)
    if not m:
        return None
    ville = m.group(1).strip(" -'")
    if _norm(ville) in ("la meteo", "meteo", "temps", "demain", "l'exterieur"):
        return None
    return ville or None


def _via_meteo(question):
    ville = ville_meteo(question)
    demain = "demain" in _norm(question)
    precision = ""
    if ville:
        try:
            geo = _get_json("https://geocoding-api.open-meteo.com/v1/search?"
                            + urllib.parse.urlencode({"name": ville, "count": 1,
                                                      "language": "fr"}))
            lieu = geo["results"][0]
            nom, lat, lon = lieu["name"], lieu["latitude"], lieu["longitude"]
        except (KeyError, IndexError):
            print("[web_search] météo : ville « {} » introuvable".format(ville))
            return None
        except Exception as err:
            print("[web_search] géocodage météo impossible :", err)
            return None
    else:
        nom, lat, lon = _POSITION_DEFAUT
        precision = " (position par défaut : GPS non branché)"
    try:
        data = _get_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "auto",
            "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,"
                     "precipitation_probability_max",
            "forecast_days": 2}))
        c, d = data["current"], data["daily"]
        if demain:
            texte = ("Demain à {}{} : {}, entre {:.0f} et {:.0f} °C, {} % de risque "
                     "de pluie.").format(
                nom, precision, _WMO.get(d["weather_code"][1], "temps variable"),
                d["temperature_2m_min"][1], d["temperature_2m_max"][1],
                d["precipitation_probability_max"][1] or 0)
        else:
            texte = ("À {}{}, il fait {:.0f} °C, {}. Vent {:.0f} km/h, humidité {} %. "
                     "Aujourd'hui : entre {:.0f} et {:.0f} °C.").format(
                nom, precision, c["temperature_2m"],
                _WMO.get(c["weather_code"], "temps variable"),
                c["wind_speed_10m"], c["relative_humidity_2m"],
                d["temperature_2m_min"][0], d["temperature_2m_max"][0])
    except Exception as err:
        print("[web_search] Open-Meteo indisponible :", err)
        return None
    return _reponse(texte, "Open-Meteo", "https://open-meteo.com/")


# ═════════════════════════════════════════════════════════════════════════
# Source 1 : DuckDuckGo Instant Answer (API)
# ═════════════════════════════════════════════════════════════════════════
def _via_duckduckgo(question):
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": question, "format": "json", "no_html": "1", "kl": "fr-fr",
        "skip_disambig": "1"})
    try:
        data = _get_json(url)
    except Exception as error:
        print("[web_search] DuckDuckGo API indisponible :", error)
        return None
    # Answer : réponse directe (calcul, conversion...) ; sinon le résumé.
    reponse = data.get("Answer")
    if isinstance(reponse, str) and reponse.strip():
        return _reponse(_nettoyer(reponse), "DuckDuckGo")
    for cle, src, url_cle in (("AbstractText", "AbstractSource", "AbstractURL"),
                              ("Definition", "DefinitionSource", "DefinitionURL")):
        texte = (data.get(cle) or "").strip()
        if texte and _pertinent(texte, question):
            return _reponse(synthese(texte, question),
                            data.get(src) or "DuckDuckGo", data.get(url_cle) or "")
    return None


# ═════════════════════════════════════════════════════════════════════════
# Source 2 : Wikipédia, résultats classés par pertinence
# ═════════════════════════════════════════════════════════════════════════
def article_hors_sujet(hit, question):
    """Écarte un article qui ne peut pas être la réponse : une année / un
    nombre de la question absent de son titre et de son extrait (« coupe
    du monde 2022 » -> pas l'article 2026), ou aucun mot en commun.

    On garde sinon l'ordre de Wikipédia : un classement « maison » par mots
    du titre faisait passer l'article « Australie » devant « Canberra » pour
    « capitale de l'Australie », alors que c'est Canberra qui répond."""
    cles = mots_cles(question)
    mots = _mots(hit.get("title", "") + " " + re.sub("<[^>]+>", "", hit.get("snippet", "")))
    if any(c not in mots for c in cles if c.isdigit()):
        return True
    return bool(cles) and not any(c in mots for c in cles)


def _via_wikipedia(question, lang="fr"):
    base = "https://{}.wikipedia.org/w/api.php?".format(lang)
    candidats = []
    # Mots-clés du sujet d'abord ; la question entière en second recours
    for termes in dict.fromkeys((mots_recherche(question), question)):
        try:
            hits = _get_json(base + urllib.parse.urlencode({
                "action": "query", "list": "search", "srsearch": termes,
                "format": "json", "srlimit": 6}))["query"]["search"]
        except Exception as error:
            print("[web_search] recherche Wikipédia ({}) impossible : {}".format(lang, error))
            return None
        candidats = [h for h in hits if not article_hors_sujet(h, question)][:3]
        if candidats:
            break
    if not candidats:
        return None
    try:
        # Introductions COMPLÈTES des candidats, en une seule requête : c'est
        # là que se trouvent le chiffre ou le fait demandé (le résumé court
        # de Sfax ne contenait pas sa population).
        pages = _get_json(base + urllib.parse.urlencode({
            "action": "query", "prop": "extracts|info", "exintro": 1,
            "explaintext": 1, "inprop": "url", "redirects": 1,
            "titles": "|".join(h["title"] for h in candidats),
            "format": "json"}))["query"]["pages"]
    except Exception as error:
        print("[web_search] extraits Wikipédia ({}) impossibles : {}".format(lang, error))
        return None
    par_titre = {p.get("title"): p for p in pages.values()}
    cles = _cles_etendues(question)

    def note(rang, hit):
        page = par_titre.get(hit["title"]) or {}
        extrait = page.get("extract") or ""
        meilleure = max((len(cles & _mots(ph)) for ph in _phrases(extrait)), default=0)
        # L'ordre de Wikipédia reste le critère de départage : un article
        # doit répondre nettement mieux pour passer devant.
        return meilleure - 0.6 * rang

    classes = sorted(enumerate(candidats), key=lambda rh: -note(*rh))
    for _rang, hit in classes:
        page = par_titre.get(hit["title"]) or {}
        extrait = (page.get("extract") or "").strip()
        if extrait and _pertinent(hit["title"] + " " + extrait, question):
            nom = "Wikipédia" if lang == "fr" else "Wikipedia ({})".format(lang)
            return _reponse(synthese(extrait, question), nom, page.get("fullurl", ""))
    return None


# ═════════════════════════════════════════════════════════════════════════
# Source 3 : scraping léger d'un moteur de recherche
# ═════════════════════════════════════════════════════════════════════════
def _texte_html(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def _url_ddg(href):
    """Les liens DuckDuckGo passent par //duckduckgo.com/l/?uddg=<vraie URL>."""
    q = urllib.parse.urlparse(html.unescape(href)).query
    cible = urllib.parse.parse_qs(q).get("uddg")
    return cible[0] if cible else html.unescape(href)


def parse_ddg_html(page):
    resultats = []
    blocs = re.split(r'(?=<div class="result results_links)', page)[1:]
    for bloc in blocs:
        if "result--ad" in bloc[:300]:
            continue        # publicité
        a = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', bloc, re.S)
        s = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', bloc, re.S)
        if a and s:
            resultats.append({"titre": _texte_html(a.group(2)), "url": _url_ddg(a.group(1)),
                              "extrait": _texte_html(s.group(1))})
    return resultats


def parse_bing_html(page):
    resultats = []
    for bloc in re.findall(r'<li class="b_algo".*?</li>', page, re.S):
        a = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', bloc, re.S)
        p = re.search(r'<p[^>]*>(.*?)</p>', bloc, re.S)
        if a and p:
            resultats.append({"titre": _texte_html(a.group(2)), "url": html.unescape(a.group(1)),
                              "extrait": _texte_html(p.group(1))})
    return resultats


def _page_anti_robot(code, page):
    bas = page[:20000].lower()
    return code == 202 or "anomaly" in bas or "captcha" in bas or "unusual traffic" in bas


_MOTEURS = [
    ("DuckDuckGo", lambda q: _get("https://html.duckduckgo.com/html/", ua=BROWSER_UA,
                                  data={"q": q, "kl": "fr-fr"}), parse_ddg_html),
    ("Bing", lambda q: _get("https://www.bing.com/search?" + urllib.parse.urlencode(
        {"q": q, "setlang": "fr", "cc": "FR"}), ua=BROWSER_UA), parse_bing_html),
]


def _domaine(url):
    hote = urllib.parse.urlparse(url).netloc
    return hote[4:] if hote.startswith("www.") else hote


def _via_moteur(question):
    for nom, requete, analyse in _MOTEURS:
        if _moteurs_bloques.get(nom, 0) > time.time():
            print("[web_search] {} en pause (page anti-robot récente)".format(nom))
            continue
        try:
            code, page = requete(question)
        except Exception as error:
            print("[web_search] {} indisponible : {}".format(nom, error))
            continue
        if _page_anti_robot(code, page):
            print("[web_search] {} renvoie une page anti-robot : pause de {} min"
                  .format(nom, PAUSE_BLOCAGE // 60))
            _moteurs_bloques[nom] = time.time() + PAUSE_BLOCAGE
            continue
        resultats = [r for r in analyse(page)
                     if r["extrait"] and _pertinent(r["titre"] + " " + r["extrait"], question)]
        if not resultats:
            print("[web_search] {} : aucun résultat exploitable".format(nom))
            continue
        # Extrait du 1er résultat, complété par le 2e s'il est court
        texte = resultats[0]["extrait"]
        if len(texte) < 160 and len(resultats) > 1:
            texte += " " + resultats[1]["extrait"]
        return _reponse(synthese(texte.replace("...", "."), question),
                        _domaine(resultats[0]["url"]) or nom, resultats[0]["url"])
    return None


# ═════════════════════════════════════════════════════════════════════════
# Point d'entrée
# ═════════════════════════════════════════════════════════════════════════
def answer(question):
    """Répond à `question`. Renvoie un dict :
      {"ok": True, "texte", "source", "url"}   réponse trouvée
      {"ok": False, "raison": "hors_ligne" | "rien"}
    N'invente jamais : sans source fiable, ok=False.
    """
    question = (question or "").strip()
    if not question:
        return {"ok": False, "raison": "rien"}
    if not is_online():
        return {"ok": False, "raison": "hors_ligne"}

    if est_meteo(question):
        meteo = _via_meteo(question)
        if meteo is not None:
            return meteo

    wiki_fr = lambda q: _via_wikipedia(q, "fr")
    wiki_en = lambda q: _via_wikipedia(q, "en")
    ordre = [_via_duckduckgo, wiki_fr, wiki_en, _via_moteur]
    if est_actualite(question):
        # Une encyclopédie ne connaît ni les prix ni les scores du jour
        ordre = [_via_duckduckgo, _via_moteur, wiki_fr, wiki_en]
    for source in ordre:
        resultat = source(question)
        if resultat and resultat.get("ok") and resultat.get("texte"):
            if est_actualite(question) and source in (wiki_fr, wiki_en):
                # Honnêteté : l'encyclopédie n'a pas le prix / le score du
                # jour, on le dit au lieu de faire passer une définition
                # pour la réponse.
                resultat["texte"] = ("Je n'ai pas trouvé d'information à jour. "
                                     "Voici ce que dit l'encyclopédie : " + resultat["texte"])
            return resultat
    return {"ok": False, "raison": "rien"}


# --- compatibilité avec l'ancienne interface ------------------------------
def search(query, limit=3):
    """Ancienne interface : liste [{"titre", "extrait", "url"}]."""
    r = answer(query)
    return [{"titre": r["source"], "extrait": r["texte"], "url": r["url"]}] if r.get("ok") else []


def format_for_speech(resultats, query):
    """Ancienne interface : texte de la 1re réponse (jamais d'URL brute)."""
    return resultats[0]["extrait"] if resultats else None
