#!/usr/bin/env python3
"""Tests du chemin rapide de l'assistant (commandes traitées sans Qwen).

L'horloge est figée au jeudi 24 septembre 2026, 14:00 : les délais relatifs
(« dans 30 minutes ») et les dates sans année (« le 15 mars ») donnent alors
un résultat exact et reproductible.
"""

import sys
from datetime import datetime as _vrai_datetime
from pathlib import Path

import pytest

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova import assistant_actions as aa


class _Horloge(_vrai_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 24, 14, 0)


@pytest.fixture(autouse=True)
def horloge_figee(monkeypatch):
    monkeypatch.setattr(aa, "datetime", _Horloge)


def rdv(texte):
    r = aa.try_fast_path(texte)
    assert r is not None and r["action"] == "ajouter_evenement", r
    return r["titre"], r["date"], r["heure"]


# ─── délais relatifs calculés en Python ─────────────────────────────────
@pytest.mark.parametrize("texte, attendu", [
    ("rappelle-moi dans 30 minutes d'appeler Karim", ("Appeler Karim", "2026-09-24", "14:30")),
    ("rappelle-moi dans une heure de boire de l'eau", ("Boire de l'eau", "2026-09-24", "15:00")),
    ("rappelle-moi dans une demi-heure", ("Rappel", "2026-09-24", "14:30")),
    ("rappelle-moi dans un quart d'heure de sortir", ("Sortir", "2026-09-24", "14:15")),
    ("rappelle-moi dans 1h30 de sortir le chien", ("Sortir le chien", "2026-09-24", "15:30")),
    ("rappelle-moi dans deux heures et quart de manger", ("Manger", "2026-09-24", "16:15")),
    ("rappelle-moi dans vingt-cinq minutes de vérifier le four", ("Vérifier le four", "2026-09-24", "14:25")),
    ("rappelle-moi dans quatorze minutes", ("Rappel", "2026-09-24", "14:14")),
    ("rappelle-moi dans 3 jours à 10h d'aller à la banque", ("Aller à la banque", "2026-09-27", "10:00")),
    ("rappelle-moi dans 12 heures de prendre le médicament", ("Prendre le médicament", "2026-09-25", "02:00")),
])
def test_delais_relatifs(texte, attendu):
    assert rdv(texte) == attendu


# ─── dates absolues ─────────────────────────────────────────────────────
def test_mois_en_lettres_passe_bascule_annee_suivante():
    assert rdv("ajoute un rendez-vous le 15 mars à 10h chez le dentiste") == (
        "Chez le dentiste", "2027-03-15", "10:00")


def test_mois_en_lettres_avec_jour_de_semaine():
    assert rdv("ajoute un rendez-vous mardi 1er décembre à 14h30 réunion de chantier") == (
        "Réunion de chantier", "2026-12-01", "14:30")


def test_annee_explicite_respectee():
    assert rdv("ajoute un rdv le 2 janvier 2028 à 8h bilan")[1] == "2028-01-02"


def test_titre_par_defaut():
    assert rdv("ajoute un rendez-vous demain à 10h") == ("Rendez-vous", "2026-09-25", "10:00")


# ─── dates / heures invalides : refus poli ──────────────────────────────
@pytest.mark.parametrize("texte, extrait", [
    ("ajoute un rendez-vous le 32 janvier à 10h dentiste", "janvier ne compte que 31 jours"),
    ("ajoute un rdv le 31/04 à 9h réunion", "avril ne compte que 30 jours"),
    ("ajoute un rdv le 29 février à 9h", "n'existe pas en 2027"),
    ("ajoute un rdv le 2026-02-30 à 9h", "février ne compte que 28 jours"),
    ("ajoute un rdv demain à 25h réunion", "n'est pas une heure valide"),
])
def test_dates_invalides(texte, extrait):
    r = aa.try_fast_path(texte)
    assert r["action"] == "date_invalide"
    assert extrait in r["message"]
    assert extrait in aa.execute_action(r)


# ─── routage sans LLM ───────────────────────────────────────────────────
@pytest.mark.parametrize("texte, attendu", [
    ("mets le volume à 40", {"action": "regler_volume", "valeur": 40}),
    ("monte le volume", {"action": "regler_volume", "delta": 10}),
    ("coupe le son", {"action": "regler_volume", "valeur": 0}),
    ("règle la luminosité à 30", {"action": "regler_luminosite", "valeur": 30}),
    ("active le wifi", {"action": "wifi", "actif": True}),
    ("coupe le bluetooth", {"action": "bluetooth", "actif": False}),
    ("désactive les notifications", {"action": "notifications", "actif": False}),
    ("emmène-moi à Sousse", {"action": "naviguer", "destination": "Sousse"}),
    ("itinéraire vers Hammam-Lif", {"action": "naviguer", "destination": "Hammam-Lif"}),
    ("où suis-je", {"action": "ma_position"}),
    ("quelle est la température", {"action": "lire_capteur", "capteur": "temperature"}),
    ("état des capteurs", {"action": "etat_capteurs"}),
    ("qu'est-ce que j'ai demain", {"action": "voir_evenements", "date": "2026-09-25"}),
    ("mon prochain rendez-vous", {"action": "prochain_evenement"}),
    ("ouvre mon agenda", {"action": "ouvrir_app", "app": "calendar"}),
    ("règle la radio sur 98.5", {"action": "regler_frequence", "valeur": 98.5}),
    ("mets 101,3 MHz", {"action": "regler_frequence", "valeur": 101.3}),
    ("bonjour", {"action": "petite_phrase", "genre": "salut"}),
    ("merci", {"action": "petite_phrase", "genre": "merci"}),
])
def test_routage_rapide(texte, attendu):
    assert aa.try_fast_path(texte) == attendu


@pytest.mark.parametrize("texte", [
    "envoie un SMS à maman", "appelle Karim", "joue de la musique",
    "lis mes mails", "mets une alarme à 7h", "ouvre youtube",
])
def test_capacites_absentes_refus_honnete(texte):
    r = aa.try_fast_path(texte)
    assert r["action"] == "non_disponible"
    assert aa.execute_action(r).startswith("Je n'ai pas encore la fonctionnalité")


@pytest.mark.parametrize("texte", [
    # Doivent rester au LLM : aucune action ne doit être devinée à tort.
    "raconte-moi une blague",
    "comment s'appelle le président de la Tunisie",   # « s'appelle » != appel
])
def test_laisse_au_llm(texte):
    assert aa.try_fast_path(texte) is None


def test_salutation_suivie_d_une_commande_execute_la_commande():
    r = aa.try_fast_path("bonjour, ajoute un rendez-vous demain à 9h dentiste")
    assert r["action"] == "ajouter_evenement" and r["titre"] == "Dentiste"


def test_capteurs_annonces_simules_sans_ecran():
    # Sans app Capteurs joignable, une valeur ne doit jamais passer pour réelle.
    assert "simulee" in aa.execute_action({"action": "lire_capteur", "capteur": "temperature"})
