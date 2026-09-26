#!/usr/bin/env python3
"""Tests du moteur IA avec un faux Qwen (aucun modèle chargé).

Vérifie que NOVA n'affiche jamais de JSON brut ni une action inventée par
le LLM, et que Whisper est chargé sans accès réseau.
"""

import sys
import threading
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from nova import ai_engine


class FauxQwen:
    """Renvoie, dans l'ordre, les réponses scriptées (en streaming)."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []

    def create_chat_completion(self, messages, stream=False, **kwargs):
        self.appels.append(messages)
        texte = self.reponses.pop(0)
        if not stream:
            return {"choices": [{"message": {"content": texte}}]}
        return iter([{"choices": [{"delta": {"content": texte}}]}])


def moteur(reponses):
    """AssistantEngine sans chargement réel des modèles."""
    eng = object.__new__(ai_engine.AssistantEngine)
    eng.llm = type("L", (), {})()
    eng.llm.ready = True
    eng.llm.model = FauxQwen(reponses)
    eng.history = []
    eng._llm_lock = threading.Lock()
    eng._remember = lambda role, content: None
    return eng


def test_action_inventee_relance_en_texte():
    eng = moteur(['{"action": "traduire_texte", "texte": "bonne nuit"}',
                  "« Bonne nuit » se dit « good night »."])
    assert eng.respond("traduis bonne nuit en anglais") == "« Bonne nuit » se dit « good night »."
    assert len(eng.llm.model.appels) == 2        # une seule relance


def test_action_inventee_deux_fois_refus_honnete():
    eng = moteur(['{"action": "commander_pizza"}', '{"action": "commander_pizza"}'])
    assert eng.respond("commande une pizza") == "Je n'ai pas encore cette fonctionnalité."


def test_json_illisible_jamais_affiche():
    eng = moteur(['{"action": "ajouter_even'])
    reponse = eng.respond("un truc ambigu qui part au LLM")
    assert "{" not in reponse


def test_texte_libre_diffuse():
    vus = []
    eng = moteur(["Rome est la capitale de l'Italie."])
    eng.respond("capitale de l'Italie ?", on_token=vus.append)
    assert "".join(vus) == "Rome est la capitale de l'Italie."


def test_whisper_charge_sans_reseau(monkeypatch):
    recu = {}

    class FauxWhisper:
        def __init__(self, nom, **kwargs):
            recu.update(kwargs)

    import types
    # Faux module : le test ne dépend pas de l'installation de faster-whisper
    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.SimpleNamespace(WhisperModel=FauxWhisper))
    ai_engine.SpeechToText(model_name="small")
    assert recu.get("local_files_only") is True
