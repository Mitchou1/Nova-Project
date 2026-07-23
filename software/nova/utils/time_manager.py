#!/usr/bin/env python3
"""Gestion du temps, des alarmes et des tâches périodiques."""

from datetime import datetime, timedelta


class TimeManager:
    """Encapsule APScheduler (optionnel : dégradation propre s'il manque)."""

    def __init__(self):
        self.scheduler = None
        self.jobs = []

    def start(self):
        if self.scheduler is not None:
            return True
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            print("[time] APScheduler absent : rappels desactives")
            return False
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        return True

    def add_alarm(self, callback, trigger_time):
        """Programme un rappel à une date/heure précise."""
        if not self.start():
            return None
        job = self.scheduler.add_job(callback, "date", run_date=trigger_time)
        self.jobs.append(job)
        return job

    def add_in(self, callback, seconds):
        """Programme un rappel dans N secondes."""
        return self.add_alarm(callback, datetime.now() + timedelta(seconds=seconds))

    def add_recurring(self, callback, interval_seconds):
        """Programme une tâche récurrente."""
        if not self.start():
            return None
        job = self.scheduler.add_job(callback, "interval", seconds=interval_seconds)
        self.jobs.append(job)
        return job

    def shutdown(self):
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
        self.jobs = []


_instance = None


def get_time_manager():
    global _instance
    if _instance is None:
        _instance = TimeManager()
    return _instance
