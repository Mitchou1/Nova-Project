#!/usr/bin/env python3
"""Tests de la couche de stockage de l'agenda."""

import sys
from datetime import datetime
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
    db = tmp_path / "test_calendar.db"
    today = datetime.now().strftime("%Y-%m-%d")

    storage.init_db(db)
    storage.add_event("Rappel", today, "00:01", db_path=db)

    first = storage.due_reminders(db_path=db)
    second = storage.due_reminders(db_path=db)
    assert len(first) == 1
    assert second == []
