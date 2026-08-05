#!/usr/bin/env python3
"""Recherche web pour NOVA — capacité "JARVIS" : interroger le web et
répondre avec de vraies informations, pas seulement piloter l'appareil.

Contrairement au reste de NOVA (conçu pour marcher hors ligne), ceci a
BESOIN d'internet. Deux sources, dans l'ordre :

  1. DuckDuckGo Instant Answer API (api.duckduckgo.com) — rapide, une
     seule requête, bon sur les questions factuelles directes.
  2. Wikipédia FR (recherche + résumé) — filet de sécurité plus large,
     deux requêtes, couvre beaucoup plus de sujets.

Les deux sont des API JSON documentées, sans clé. Le HTML de recherche
DuckDuckGo classique a été essayé en premier et abandonné : il renvoie une
page anti-bot ("anomaly.js") plutôt que des résultats depuis ce type
d'environnement — pas fiable, donc pas utilisé ici.

Échoue toujours proprement (liste vide) si hors ligne ou si rien n'est
trouvé, sans jamais lever d'exception vers l'appelant.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "NOVA-Wearable/1.0 (personal project; contact: mitchou425@gmail.com)"
TIMEOUT = 6


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_online(timeout=3):
    """Verification rapide et non bloquante d'une connexion internet.

    Interroge un vrai nom de domaine plutot qu'une IP nue : certains
    reseaux/proxys renvoient 403 sur un acces direct par IP (ex. 1.1.1.1)
    sans que cela signifie une absence de connexion.
    """
    try:
        req = urllib.request.Request(
            "https://duckduckgo.com/", headers={"User-Agent": USER_AGENT})
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def _via_duckduckgo(query):
    """API Instant Answer : bon sur les questions factuelles directes."""
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query, "format": "json", "no_html": "1", "kl": "fr-fr",
    })
    try:
        data = _get_json(url)
    except Exception as error:
        print("[web_search] DuckDuckGo indisponible :", error)
        return []

    resultats = []
    texte = (data.get("AbstractText") or "").strip()
    if texte:
        resultats.append({
            "titre": data.get("Heading") or query,
            "extrait": texte,
            "url": data.get("AbstractURL") or "",
        })
    for sujet in data.get("RelatedTopics", [])[:3]:
        texte = (sujet.get("Text") or "").strip() if isinstance(sujet, dict) else ""
        if texte:
            resultats.append({
                "titre": texte.split(" - ")[0][:60],
                "extrait": texte,
                "url": sujet.get("FirstURL", "") if isinstance(sujet, dict) else "",
            })
    return resultats


def _via_wikipedia(query, lang="fr"):
    """Recherche Wikipedia puis resume de l'article le plus pertinent."""
    try:
        surl = "https://{}.wikipedia.org/w/api.php?".format(lang) + urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "format": "json", "srlimit": 3,
        })
        hits = _get_json(surl)["query"]["search"]
    except Exception as error:
        print("[web_search] recherche Wikipedia impossible :", error)
        return []

    resultats = []
    for hit in hits:
        titre = hit.get("title")
        if not titre:
            continue
        try:
            surl2 = "https://{}.wikipedia.org/api/rest_v1/page/summary/{}".format(
                lang, urllib.parse.quote(titre))
            resume = _get_json(surl2)
        except Exception:
            continue
        extrait = (resume.get("extract") or "").strip()
        if extrait:
            resultats.append({
                "titre": titre,
                "extrait": extrait,
                "url": (resume.get("content_urls", {}).get("desktop", {}) or {}).get("page", ""),
            })
        if len(resultats) >= 2:
            break
    return resultats


def search(query, limit=3):
    """Cherche `query` sur le web. Renvoie une liste de
    {"titre", "extrait", "url"} (vide si hors ligne / rien trouve).

    N'echoue jamais par exception : les deux sources internes protegent
    deja leurs propres appels reseau.
    """
    query = (query or "").strip()
    if not query:
        return []

    resultats = _via_duckduckgo(query)
    if not resultats:
        resultats = _via_wikipedia(query)
    return resultats[:limit]


def format_for_speech(resultats, query):
    """Formate des resultats en reponse parlee courte — jamais d'URL brute,
    la synthese vocale la lirait lettre par lettre."""
    if not resultats:
        return None
    premier = resultats[0]
    reponse = premier["extrait"]
    if len(resultats) > 1 and resultats[1]["extrait"]:
        reponse += " Par ailleurs, {} : {}".format(
            resultats[1]["titre"], resultats[1]["extrait"])
    return reponse
