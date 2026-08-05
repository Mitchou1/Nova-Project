#!/usr/bin/env python3
"""
Gestion du temps et des alarmes
"""

from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

class TimeManager:
    """Gestionnaire de temps et de rappels"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.alarms = []

    def add_alarm(self, callback, trigger_time):
        """Ajoute un rappel"""
        job = self.scheduler.add_job(
            callback,
            'date',
            run_date=trigger_time
        )
        self.alarms.append(job)
        return job

    def add_recurring(self, callback, interval_seconds):
        """Ajoute une tâche récurrente"""
        return self.scheduler.add_job(
            callback,
            'interval',
            seconds=interval_seconds
        )

    def shutdown(self):
        """Arrête le scheduler"""
        self.scheduler.shutdown()

time_manager = TimeManager()
