#!/usr/bin/env python3
"""Accès SQLite de l'agenda (séparé de l'UI pour être testable seul)."""

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
"""


def connect(db_path=None):
    path = db_path or CALENDAR_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path=None):
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)
    return True


def add_event(title, date, time, priority=1, description="", reminder=10, db_path=None):
    init_db(db_path)
    with connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO events (title, event_date, event_time, priority, "
            "description, reminder_minutes) VALUES (?, ?, ?, ?, ?, ?)",
            (title, date, time, priority, description, reminder),
        )
        return cursor.lastrowid


def get_events_for(date_str, db_path=None):
    init_db(db_path)
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE event_date = ? ORDER BY event_time",
            (date_str,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_today_events(db_path=None):
    return get_events_for(datetime.now().strftime("%Y-%m-%d"), db_path)


def delete_event(event_id, db_path=None):
    with connect(db_path) as connection:
        connection.execute("DELETE FROM events WHERE id = ?", (event_id,))
    return True


def due_reminders(within_minutes=10, db_path=None):
    """Événements dont le rappel doit être déclenché maintenant."""
    init_db(db_path)
    now = datetime.now()
    limit = (now + timedelta(minutes=within_minutes)).strftime("%H:%M")
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE event_date = ? AND event_time <= ? "
            "AND notified = 0 ORDER BY event_time",
            (now.strftime("%Y-%m-%d"), limit),
        ).fetchall()
        events = [dict(row) for row in rows]
        for event in events:
            connection.execute(
                "UPDATE events SET notified = 1 WHERE id = ?", (event["id"],))
    return events


def next_event_label(db_path=None):
    """Libellé du prochain événement du jour, pour l'écran d'accueil."""
    now = datetime.now()
    current = now.strftime("%H:%M")
    for event in get_today_events(db_path):
        if event["event_time"] >= current:
            return "{}  {}".format(event["event_time"], event["title"])
    return "Aucun evenement prevu"
