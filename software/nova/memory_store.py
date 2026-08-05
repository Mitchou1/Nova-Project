#!/usr/bin/env python3
"""Mémoire persistante de NOVA (JARVIS v2.0, partie réaliste) :

  - historique de conversation qui survit aux redémarrages (jusqu'ici en
    mémoire seulement dans AssistantEngine.history, perdu à chaque relance)
  - compteur de fréquence (apps/actions/destinations les plus utilisées) —
    une base STATISTIQUE simple, explicitement pas de l'apprentissage
    automatique : pas de modèle entraîné, juste des comptes SQL.

Suit le même schéma d'accès que apps/calendar/storage.py (connexion fermée
à chaque appel via un context manager dédié, cf. audit qui avait trouvé la
fuite de connexions sur ce fichier).
"""

import contextlib
import sqlite3
from datetime import datetime

from nova.paths import DATA_DIR

MEMORY_DB = DATA_DIR / "memory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS frequency (
    category TEXT NOT NULL,
    value TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    last_used TEXT,
    PRIMARY KEY (category, value)
);
"""


def _connect(db_path=None):
    path = db_path or MEMORY_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


@contextlib.contextmanager
def _session(db_path=None):
    connection = _connect(db_path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(db_path=None):
    with _session(db_path) as connection:
        connection.executescript(SCHEMA)
    return True


# ─────────────────────────────────────────────────────────────────────────
# Historique de conversation persistant
# ─────────────────────────────────────────────────────────────────────────
def append_turn(role, content, db_path=None, max_turns=6):
    """Ajoute un tour et purge au-dela de max_turns*2 messages (meme limite
    que la fenetre glissante en memoire de AssistantEngine)."""
    if not content:
        return
    init_db(db_path)
    with _session(db_path) as connection:
        connection.execute(
            "INSERT INTO conversation (role, content, created_at) VALUES (?, ?, ?)",
            (role, content, datetime.now().isoformat()))
        limite = max_turns * 2
        connection.execute(
            "DELETE FROM conversation WHERE id NOT IN "
            "(SELECT id FROM conversation ORDER BY id DESC LIMIT ?)",
            (limite,))


def load_history(db_path=None, max_turns=6):
    """Historique persiste, dans l'ordre chronologique — pret a etre injecte
    tel quel dans les messages envoyes au LLM."""
    init_db(db_path)
    with _session(db_path) as connection:
        rows = connection.execute(
            "SELECT role, content FROM conversation ORDER BY id ASC LIMIT ?",
            (max_turns * 2,)).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def clear_history(db_path=None):
    init_db(db_path)
    with _session(db_path) as connection:
        connection.execute("DELETE FROM conversation")


# ─────────────────────────────────────────────────────────────────────────
# Compteur de frequence (statistique simple, pas de ML)
# ─────────────────────────────────────────────────────────────────────────
def note_usage(category, value, db_path=None):
    """Incremente le compteur pour (category, value).
    Ex: note_usage("action", "ouvrir_app"), note_usage("destination", "Sousse")."""
    if not value:
        return
    init_db(db_path)
    with _session(db_path) as connection:
        connection.execute(
            "INSERT INTO frequency (category, value, count, last_used) "
            "VALUES (?, ?, 1, ?) "
            "ON CONFLICT(category, value) DO UPDATE SET "
            "count = count + 1, last_used = excluded.last_used",
            (category, value, datetime.now().isoformat()))


def top_usage(category, limit=5, db_path=None):
    """Valeurs les plus frequentes d'une categorie, triees par frequence
    puis recence (depart egalite)."""
    init_db(db_path)
    with _session(db_path) as connection:
        rows = connection.execute(
            "SELECT value, count FROM frequency WHERE category = ? "
            "ORDER BY count DESC, last_used DESC LIMIT ?",
            (category, limit)).fetchall()
    return [{"value": row["value"], "count": row["count"]} for row in rows]
