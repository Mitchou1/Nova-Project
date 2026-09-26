#!/usr/bin/env python3
"""Tests de la recherche web, SANS réseau (toutes les réponses sont simulées).

Couvre : nettoyage et synthèse du texte, rejet des articles hors sujet,
ordre de la cascade, pages anti-robot, analyse du HTML des moteurs, et
messages honnêtes hors ligne ou sans résultat.
"""

import sys
import time
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova import web_search as ws
from nova import assistant_actions as aa


# ─── nettoyage / synthèse ───────────────────────────────────────────────
def test_nettoyage_parenthese_orpheline_et_arabe():
    # Texte réel de Wikipédia : parenthèse jamais refermée + nom en arabe
    brut = ("Ibn Khaldoun (en arabe\xa0:\xa0[ɪbn̩ χɐlduːn]; nom complet\xa0: "
            "أبو زيد عبد الرحمن, né le 27 mai 1332 à Tunis, est un historien.")
    assert ws._nettoyer(brut) == "Ibn Khaldoun, né le 27 mai 1332 à Tunis, est un historien."


def test_nettoyage_phonetique_et_parentheses():
    assert ws._nettoyer("Paris (prononcé [paʁi]) est une ville.") == "Paris est une ville."
    # parenthèse courte et utile : gardée
    assert ws._nettoyer("La tour fait 330 m (avec antennes) de haut.") == \
        "La tour fait 330 m (avec antennes) de haut."


def test_decoupage_en_phrases():
    assert ws._phrases("Il naît en 52 av. J.-C. Il meurt à Rome. Fin.") == \
        ["Il naît en 52 av. J.-C.", "Il meurt à Rome.", "Fin."]
    assert ws._phrases("M. Dupont arrive. Il part.") == ["M. Dupont arrive.", "Il part."]


def test_synthese_2_a_4_phrases_et_phrase_pertinente():
    texte = ("Sfax est une ville de Tunisie. Elle est portuaire. Son climat est doux. "
             "Sfax compte 600 000 habitants en 2019. Elle a une médina. Le port exporte.")
    r = ws.synthese(texte, "population de Sfax")
    assert r.startswith("Sfax est une ville de Tunisie.")
    assert "600 000 habitants" in r            # synonyme population -> habitants
    assert 2 <= len(ws._phrases(r)) <= 4


def test_annee_differente_hors_sujet():
    q = "qui a gagné la coupe du monde 2022"
    assert ws.article_hors_sujet({"title": "Coupe du monde de football 2026", "snippet": ""}, q)
    assert not ws.article_hors_sujet({"title": "Coupe du monde de football 2022", "snippet": ""}, q)


def test_mots_recherche_sans_verbe_de_reponse():
    assert ws.mots_recherche("qui a gagné la coupe du monde 2022") == "coupe monde 2022"


def test_detection_intentions():
    assert ws.est_meteo("quel temps fait-il à Sfax")
    assert ws.est_meteo("météo demain")
    assert ws.est_actualite("prix du bitcoin aujourd'hui")
    assert not ws.est_actualite("qui est Ibn Khaldoun")
    assert ws.ville_meteo("météo à Sousse demain") == "Sousse"
    assert ws.ville_meteo("la météo") is None


# ─── analyse HTML des moteurs ───────────────────────────────────────────
DDG_HTML = """
<div class="result results_links results_links_deep result--ad">
  <a class="result__a" href="https://pub.example/">Pub</a>
  <a class="result__snippet" href="x">Achetez maintenant</a></div>
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title"><a rel="nofollow" class="result__a"
   href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.coinbase.com%2Fprice%2Fbitcoin&amp;rut=abc">
   Prix du <b>Bitcoin</b></a></h2>
  <a class="result__snippet" href="x">Le cours du <b>Bitcoin</b> est de 58 000 &euro; aujourd&#x27;hui.</a>
</div>"""

BING_HTML = """<ol><li class="b_algo"><h2><a href="https://fr.example.org/btc">Bitcoin cours</a></h2>
<div class="b_caption"><p>Le prix du bitcoin atteint 58 000 euros.</p></div></li></ol>"""


def test_parse_ddg_html_ignore_pub_et_decode_url():
    r = ws.parse_ddg_html(DDG_HTML)
    assert len(r) == 1
    assert r[0]["url"] == "https://www.coinbase.com/price/bitcoin"
    assert r[0]["extrait"] == "Le cours du Bitcoin est de 58 000 € aujourd'hui."


def test_parse_bing_html():
    assert ws.parse_bing_html(BING_HTML) == [{
        "titre": "Bitcoin cours", "url": "https://fr.example.org/btc",
        "extrait": "Le prix du bitcoin atteint 58 000 euros."}]


def test_page_anti_robot_met_le_moteur_en_pause(monkeypatch):
    ws._moteurs_bloques.clear()
    appels = []

    def faux_ddg(q):
        appels.append("ddg")
        return 202, "<html>anomaly-modal</html>"
    monkeypatch.setattr(ws, "_MOTEURS", [("DuckDuckGo", faux_ddg, ws.parse_ddg_html),
                                         ("Bing", lambda q: (200, BING_HTML), ws.parse_bing_html)])
    r = ws._via_moteur("prix du bitcoin")
    assert r["source"] == "fr.example.org" and "58 000" in r["texte"]
    assert ws._moteurs_bloques["DuckDuckGo"] > time.time()
    ws._via_moteur("prix du bitcoin")
    assert appels == ["ddg"]        # pas réinterrogé pendant la pause
    ws._moteurs_bloques.clear()


# ─── cascade ────────────────────────────────────────────────────────────
def _sources(monkeypatch, ddg=None, wiki=None, moteur=None, meteo=None, online=True):
    ordre = []

    def fab(nom, valeur):
        def f(q, *a):
            ordre.append(nom)
            return valeur
        return f
    monkeypatch.setattr(ws, "is_online", lambda timeout=3: online)
    monkeypatch.setattr(ws, "_via_duckduckgo", fab("ddg", ddg))
    monkeypatch.setattr(ws, "_via_wikipedia", fab("wiki", wiki))
    monkeypatch.setattr(ws, "_via_moteur", fab("moteur", moteur))
    monkeypatch.setattr(ws, "_via_meteo", fab("meteo", meteo))
    return ordre


def test_cascade_encyclopedique(monkeypatch):
    ordre = _sources(monkeypatch, wiki={"ok": True, "texte": "Canberra.",
                                        "source": "Wikipédia", "url": ""})
    assert ws.answer("capitale de l'Australie")["texte"] == "Canberra."
    assert ordre == ["ddg", "wiki"]


def test_cascade_actualite_moteur_avant_wikipedia(monkeypatch):
    ordre = _sources(monkeypatch, moteur={"ok": True, "texte": "58 000 €.",
                                          "source": "x", "url": ""})
    ws.answer("prix du bitcoin")
    assert ordre == ["ddg", "moteur"]


def test_actualite_sans_info_a_jour_le_dit(monkeypatch):
    _sources(monkeypatch, wiki={"ok": True, "texte": "Le Bitcoin est une cryptomonnaie.",
                                "source": "Wikipédia", "url": ""})
    r = ws.answer("prix du bitcoin")
    assert r["texte"].startswith("Je n'ai pas trouvé d'information à jour.")


def test_meteo_passe_par_open_meteo(monkeypatch):
    ordre = _sources(monkeypatch, meteo={"ok": True, "texte": "22 °C.",
                                         "source": "Open-Meteo", "url": ""})
    assert ws.answer("météo à Tunis")["source"] == "Open-Meteo"
    assert ordre == ["meteo"]


def test_hors_ligne_aucune_source_interrogee(monkeypatch):
    ordre = _sources(monkeypatch, online=False)
    assert ws.answer("qui est Ibn Khaldoun") == {"ok": False, "raison": "hors_ligne"}
    assert ordre == []


# ─── messages dans le chat ──────────────────────────────────────────────
def test_reponse_dans_le_chat_avec_source(monkeypatch):
    monkeypatch.setattr(ws, "answer", lambda q: {"ok": True, "texte": "Canberra est la capitale.",
                                                 "source": "Wikipédia", "url": "https://x"})
    r = aa.execute_action({"action": "rechercher_web", "requete": "capitale de l'Australie"})
    assert r == "Canberra est la capitale. Source : Wikipédia."
    assert "http" not in r          # jamais d'URL lue à voix haute


def test_hors_ligne_message_clair_sans_invention(monkeypatch):
    monkeypatch.setattr(ws, "answer", lambda q: {"ok": False, "raison": "hors_ligne"})
    r = aa.execute_action({"action": "rechercher_web", "requete": "Ibn Khaldoun"})
    assert "pas de connexion internet" in r and "inventer" in r


def test_navigateur_seulement_en_dernier_recours(monkeypatch):
    ouvert = []
    monkeypatch.setattr(aa, "_open_browser", lambda d: ouvert.append(d) or "J'ouvre la recherche.")
    monkeypatch.setattr(ws, "answer", lambda q: {"ok": True, "texte": "X.", "source": "S", "url": ""})
    aa.execute_action({"action": "rechercher_web", "requete": "a"})
    assert ouvert == []
    monkeypatch.setattr(ws, "answer", lambda q: {"ok": False, "raison": "rien"})
    r = aa.execute_action({"action": "rechercher_web", "requete": "xkqzvw"})
    assert ouvert and "aucune réponse fiable" in r


def test_meteo_routee_vers_la_recherche_web():
    assert aa.try_fast_path("quelle est la météo à Sousse")["action"] == "rechercher_web"
    assert aa.try_fast_path("quelle est la température à Paris")["action"] == "rechercher_web"
    # sans lieu : c'est le capteur de l'appareil
    assert aa.try_fast_path("quelle est la température")["action"] == "lire_capteur"
