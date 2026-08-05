#!/usr/bin/env python3
"""Accès SQLite de l'agenda (séparé de l'UI pour être testable seul)."""

import contextlib
import sqlite3
from datetime import datetime, timedelta

from nova.paths import CALENDAR_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    event_date TEXT NOT NULL,
    event_time TEXT NOT NULL,
    priority INTEGER DEFAULT 1,
    description TEXT DEFAULT '',
    reminder_minutes INTEGER DEFAULT 10,
    notified INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
"""


def connect(db_path=None):
    path = db_path or CALENDAR_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


@contextlib.contextmanager
def _session(db_path=None):
    """Comme connect(), mais ferme reellement la connexion en sortie.

    Audit : `with connect(...) as connection` ne fait QUE gerer la
    transaction (commit/rollback) en sqlite3 — Connection.__exit__ n'appelle
    jamais close(). due_reminders() est interroge toutes les 20s en continu
    (main.py) : sans fermeture explicite, chaque appel accumulait un
    descripteur de fichier jamais libere.
    """
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(db_path=None):
    with _session(db_path) as connection:
        connection.executescript(SCHEMA)
    return True


def add_event(title, date, time, priority=1, description="", reminder=10, db_path=None):
    init_db(db_path)
    with _session(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO events (title, event_date, event_time, priority, "
            "description, reminder_minutes) VALUES (?, ?, ?, ?, ?, ?)",
            (title, date, time, priority, description, reminder),
        )
        return cursor.lastrowid


def get_events_for(date_str, db_path=None):
    init_db(db_path)
    with _session(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE event_date = ? ORDER BY event_time",
            (date_str,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_today_events(db_path=None):
    return get_events_for(datetime.now().strftime("%Y-%m-%d"), db_path)


def delete_event(event_id, db_path=None):
    with _session(db_path) as connection:
        connection.execute("DELETE FROM events WHERE id = ?", (event_id,))
    return True


def due_reminders(db_path=None):
    """Evenements dont le rappel doit se declencher maintenant (une seule fois).

    Chaque evenement porte son propre delai (reminder_minutes) : il devient du
    des que l'heure actuelle atteint (event_time - reminder_minutes), avec une
    tolerance de 2 minutes apres l'heure de l'evenement (si l'appareil etait en
    veille au bon moment, on ne le rate pas). `notified` passe a 1 des qu'un
    evenement est renvoye : il ne redeclenche jamais.

    Audit : la requete ne regardait QUE `event_date = aujourd'hui`. Un
    evenement a 23:58 avec un rappel de 10 min a une fenetre de declenchement
    qui commence la VEILLE (23:48) — si l'appareil verifie apres minuit,
    "aujourd'hui" a change de valeur et l'evenement ne pouvait plus jamais
    etre trouve, meme si `notified` valait encore 0 : rappel perdu en
    silence. On inclut donc aussi la date d'hier ; la fenetre temporelle
    (declenche_a / +2 min) filtre deja correctement ce qui est reellement du.
    """
    init_db(db_path)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    hier = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    due = []
    with _session(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE event_date IN (?, ?) AND notified = 0 "
            "ORDER BY event_time",
            (today, hier),
        ).fetchall()
        for row in rows:
            event = dict(row)
            try:
                event_dt = datetime.strptime(
                    "{} {}".format(event["event_date"], event["event_time"][:5]),
                    "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            delai = event.get("reminder_minutes") or 0
            declenche_a = event_dt - timedelta(minutes=delai)
            if declenche_a <= now <= event_dt + timedelta(minutes=2):
                connection.execute(
                    "UPDATE events SET notified = 1 WHERE id = ?", (event["id"],))
                due.append(event)
    return due


def next_event_label(db_path=None):
    now = datetime.now()
    current = now.strftime("%H:%M")
    for event in get_today_events(db_path):
        if event["event_time"] >= current:
            return "{}  {}".format(event["event_time"], event["title"])
    return "Aucun evenement prevu"
