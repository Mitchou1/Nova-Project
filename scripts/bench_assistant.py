#!/usr/bin/env python3
"""Banc de mesure du temps de réponse de l'assistant NOVA.

Usage (depuis la racine du projet, venv activé) :
    python scripts/bench_assistant.py

Pour chaque commande : le chemin emprunté (RAPIDE = sans LLM, ou LLM) et le
temps total de réponse, plus le temps de chargement du moteur. À lancer sur
le Pi pour avoir les vrais chiffres : sur PC, Qwen tourne bien plus vite.

Le banc est isolé : rien n'est écrit dans la config, l'agenda ou
l'historique de conversation (tout est remplacé par des versions en mémoire),
et aucune action n'a d'effet sur le système.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "software"))

COMMANDES = [
    "quelle heure est-il",
    "mets le volume à 40",
    "règle la luminosité à 30",
    "active le wifi",
    "coupe le bluetooth",
    "emmène-moi à Sousse",
    "quelle est la température",
    "qu'est-ce que j'ai demain",
    "rappelle-moi dans 30 minutes d'appeler Karim",
    "rappelle-moi dans une heure de boire de l'eau",
    "ajoute un rendez-vous le 15 mars à 10h chez le dentiste",
    "ajoute un rendez-vous le 32 janvier à 10h chez le dentiste",
    "envoie un SMS à maman",
    "joue de la musique",
    "bonjour",
    "merci",
    "règle la radio sur 98.5",
    "où suis-je",
    "état des capteurs",
    "raconte-moi une blague",
]


def isoler():
    """Remplace les écritures persistantes par des versions en mémoire."""
    from nova.utils import config_loader
    config_loader.ConfigLoader.save = lambda self: None

    from nova import memory_store
    memory_store.append_turn = lambda *a, **k: None
    memory_store.load_history = lambda *a, **k: []
    memory_store.clear_history = lambda *a, **k: None
    memory_store.note_usage = lambda *a, **k: None

    from apps.calendar import storage
    agenda = []
    storage.add_event = lambda **k: agenda.append(k)
    storage.get_events_for = lambda d, **k: [e for e in agenda if e["date"] == d]

    from nova import assistant_actions
    assistant_actions._sur_pi = lambda: False   # jamais de nmcli/amixer ici
    assistant_actions._restart = lambda: "(redémarrage ignoré par le banc)"


def main():
    isoler()
    from nova import ai_engine
    from nova import assistant_actions as actions

    t0 = time.perf_counter()
    engine = ai_engine.get_engine()
    charge = time.perf_counter() - t0
    print("Chargement du moteur (Whisper + Qwen + Piper) : {:.1f} s".format(charge))
    if hasattr(engine, "warm_up"):
        # Fait au démarrage de NOVA, en arrière-plan (main.on_start) : ce
        # temps n'est plus payé par la première commande.
        t1 = time.perf_counter()
        engine.warm_up()
        print("Préchauffage de Qwen (arrière-plan au démarrage) : {:.1f} s".format(
            time.perf_counter() - t1))
    print("État :", engine.status())
    print()

    total_rapide, total_llm, n_rapide, n_llm = 0.0, 0.0, 0, 0
    print("{:<58} {:<7} {:>7}  réponse".format("commande", "chemin", "temps"))
    print("-" * 110)
    for cmd in COMMANDES:
        chemin = "RAPIDE" if actions.try_fast_path(cmd) is not None else "LLM"
        t = time.perf_counter()
        reponse = engine.respond(cmd) or ""
        dt = time.perf_counter() - t
        if chemin == "RAPIDE":
            total_rapide += dt
            n_rapide += 1
        else:
            total_llm += dt
            n_llm += 1
        print("{:<58} {:<7} {:>6.2f}s  {}".format(
            cmd[:58], chemin, dt, reponse.replace("\n", " ")[:60]))
    print("-" * 110)
    n = n_rapide + n_llm
    print("Chemin rapide : {}/{} commandes".format(n_rapide, n))
    if n_llm:
        print("Temps moyen LLM    : {:.2f} s".format(total_llm / n_llm))
    if n_rapide:
        print("Temps moyen rapide : {:.3f} s".format(total_rapide / n_rapide))
    print("Temps total        : {:.1f} s".format(total_rapide + total_llm))


if __name__ == "__main__":
    main()
