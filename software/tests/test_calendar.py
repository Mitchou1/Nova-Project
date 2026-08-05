#!/usr/bin/env python3
"""Tests de la couche de stockage de l'agenda."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from apps.calendar import storage


def test_add_and_read(tmp_path):
    db = tmp_path / "test_calendar.db"
    today = datetime.now().strftime("%Y-%m-%d")

    storage.init_db(db)
    event_id = storage.add_event("Cours ESPRIT", today, "08:30", db_path=db)
    assert event_id > 0

    events = storage.get_events_for(today, db_path=db)
    assert len(events) == 1
    assert events[0]["title"] == "Cours ESPRIT"


def test_delete(tmp_path):
    db = tmp_path / "test_calendar.db"
    today = datetime.now().strftime("%Y-%m-%d")

    storage.init_db(db)
    event_id = storage.add_event("A supprimer", today, "10:00", db_path=db)
    storage.delete_event(event_id, db_path=db)
    assert storage.get_events_for(today, db_path=db) == []


def test_reminders_marked_once(tmp_path):
    """due_reminders() respecte le delai propre a chaque evenement
    (reminder_minutes) et ne le renvoie plus jamais une fois notifie.

    Un horaire fixe ("00:01") ne marche que par coincidence selon l'heure
    d'execution du test : on planifie donc l'evenement par rapport a
    maintenant, comme le fait vraiment l'appareil.
    """
    db = tmp_path / "test_calendar.db"
    now = datetime.now()
    dans_3_min = now + timedelta(minutes=3)

    storage.init_db(db)
    storage.add_event("Rappel", dans_3_min.strftime("%Y-%m-%d"),
                      dans_3_min.strftime("%H:%M"), reminder=5, db_path=db)

    first = storage.due_reminders(db_path=db)
    second = storage.due_reminders(db_path=db)
    assert len(first) == 1
    assert second == []


def test_reminders_not_due_yet(tmp_path):
    """Un evenement dont le delai de rappel n'est pas encore atteint ne
    doit pas etre renvoye par due_reminders()."""
    db = tmp_path / "test_calendar.db"
    now = datetime.now()
    dans_1_heure = now + timedelta(hours=1)

    storage.init_db(db)
    storage.add_event("Plus tard", dans_1_heure.strftime("%Y-%m-%d"),
                      dans_1_heure.strftime("%H:%M"), reminder=5, db_path=db)

    assert storage.due_reminders(db_path=db) == []
