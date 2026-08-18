#!/usr/bin/env python3
"""Aide SQLite partagee entre apps/calendar/storage.py et nova/memory_store.py.

sqlite3.Connection.__exit__ ne gere que commit/rollback, jamais close() —
`with connect(...) as conn` seul laisse donc fuir un descripteur de fichier
a chaque appel. Les deux modules ci-dessus dupliquaient un `_session()`
identique pour corriger ca ; extrait ici pour eviter qu'un futur correctif
(timeout, mode WAL, etc.) ne soit applique a une copie et pas l'autre.
"""

import contextlib
import sqlite3


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


@contextlib.contextmanager
def session(path):
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
