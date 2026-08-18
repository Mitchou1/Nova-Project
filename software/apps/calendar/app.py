#!/usr/bin/env python3
"""
App Calendar NOVA — Calendrier intelligent complet
SQLite + rappels + interface premium
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty, ObjectProperty
from datetime import datetime, timedelta
import contextlib
import sqlite3
import os

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager
from nova.ui.widgets import GlassCard, NeonButton


# ─── MODÈLE DE DONNÉES ──────────────────────────────────────────────────────

class Event:
    """Événement calendrier."""

    def __init__(self, id=None, title="", event_date="", event_time="",
                 end_time=None, priority=1, description="", reminder_minutes=10,
                 location="", category="general", notified=False):
        self.id = id
        self.title = title
        self.event_date = event_date
        self.event_time = event_time
        self.end_time = end_time
        self.priority = priority
        self.description = description
        self.reminder_minutes = reminder_minutes
        self.location = location
        self.category = category
        self.notified = notified

    @property
    def datetime_obj(self):
        return datetime.strptime(f"{self.event_date} {self.event_time}", "%Y-%m-%d %H:%M")

    @property
    def reminder_time(self):
        return self.datetime_obj - timedelta(minutes=self.reminder_minutes)

    @property
    def time_until(self):
        delta = self.datetime_obj - datetime.now()
        if delta.total_seconds() < 0:
            return "Terminé"
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        if days > 0:
            return f"dans {days}j {hours}h"
        elif hours > 0:
            return f"dans {hours}h {minutes}min"
        else:
            return f"dans {minutes}min"


# ─── BASE DE DONNÉES ────────────────────────────────────────────────────────

class CalendarDatabase:
    """SQLite pour les événements."""

    def __init__(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "calendar.db"
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextlib.contextmanager
    def _session(self):
        """Comme _connect(), mais ferme reellement la connexion en sortie.

        `with self._connect() as conn` ne fait QUE gerer la transaction
        (commit/rollback) en sqlite3 — Connection.__exit__ n'appelle jamais
        close(). Chaque ajout/suppression via l'ecran Calendrier accumulait
        un descripteur de fichier jamais libere.
        """
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._session() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    end_time TEXT,
                    priority INTEGER DEFAULT 1,
                    description TEXT,
                    reminder_minutes INTEGER DEFAULT 10,
                    location TEXT DEFAULT '',
                    category TEXT DEFAULT 'general',
                    notified INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON events(event_date)")
            # Migration : compléter les colonnes manquantes d'une ancienne base
            # (CREATE TABLE IF NOT EXISTS ne modifie pas une table déjà présente).
            existing = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
            wanted = {
                "end_time": "TEXT",
                "priority": "INTEGER DEFAULT 1",
                "description": "TEXT",
                "reminder_minutes": "INTEGER DEFAULT 10",
                "location": "TEXT DEFAULT ''",
                "category": "TEXT DEFAULT 'general'",
                "notified": "INTEGER DEFAULT 0",
            }
            for col, decl in wanted.items():
                if col not in existing:
                    conn.execute("ALTER TABLE events ADD COLUMN {} {}".format(col, decl))

    def create(self, event):
        with self._session() as conn:
            cursor = conn.execute("""
                INSERT INTO events (title, event_date, event_time, end_time,
                    priority, description, reminder_minutes, location, category, notified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event.title, event.event_date, event.event_time, event.end_time,
                  event.priority, event.description, event.reminder_minutes,
                  event.location, event.category, int(event.notified)))
            return cursor.lastrowid

    def get_by_date(self, date_str):
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE event_date = ? ORDER BY event_time",
                (date_str,)
            ).fetchall()
            return [self._row_to_event(r) for r in rows]

    def get_upcoming(self, days=7):
        start = datetime.now().strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE event_date BETWEEN ? AND ? ORDER BY event_date, event_time",
                (start, end)
            ).fetchall()
            return [self._row_to_event(r) for r in rows]

    def delete(self, event_id):
        with self._session() as conn:
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))

    def _row_to_event(self, row):
        return Event(
            id=row["id"], title=row["title"], event_date=row["event_date"],
            event_time=row["event_time"], end_time=row["end_time"],
            priority=row["priority"], description=row["description"],
            reminder_minutes=row["reminder_minutes"], location=row["location"],
            category=row["category"], notified=bool(row["notified"])
        )


# ─── INTERFACE ────────────────────────────────────────────────────────────────

class EventCard(GlassCard):
    """Carte d'événement — charte NOVA (Stitch).

    Structure reprise de la carte « prochain événement » de la maquette :
    barre d'accent verticale à gauche, libellé en label-caps, titre en Sora,
    données en JetBrains Mono, coin haut-droit chanfreiné.
    """

    def __init__(self, event, on_delete=None, **kwargs):
        self.event = event
        self.on_delete = on_delete
        super().__init__(size_hint=(1, None), height=dp(88),
                         corner_radius=dp(2), chamfer=dp(8),
                         scanline_enabled=True, **kwargs)
        self._build()

    def _build(self):
        from nova import fonts as _f
        from kivy.graphics import Color, Rectangle

        # Barre d'accent verticale (couleur = priorité), comme dans la maquette
        prio_colors = {
            1: theme_manager.get_color("text_secondary"),
            2: theme_manager.get_color("primary"),
            3: theme_manager.get_color("warning"),
            4: theme_manager.get_color("error"),
        }
        accent = prio_colors.get(self.event.priority,
                                 theme_manager.get_color("primary"))
        with self.canvas.after:
            self._accent_color = Color(*accent)
            self._accent_bar = Rectangle()
        self.bind(pos=self._refresh_accent, size=self._refresh_accent)

        # Heure — data-mono, couleur primaire
        self.add_widget(Label(
            text=self.event.event_time[:5],
            font_name=_f.FONT_MONO, font_size=dp(17),
            color=theme_manager.get_color("primary"),
            pos_hint={'x': 0.04, 'center_y': 0.5},
            size_hint=(0.14, 0.5),
        ))

        # Libellé catégorie — label-caps (mono, majuscules, espacé)
        categorie = (getattr(self.event, "category", "") or "ÉVÉNEMENT").upper()
        self.add_widget(Label(
            text=" ".join(categorie[:14]),   # letter-spacing simulé
            font_name=_f.FONT_MONO, font_size=dp(8),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'x': 0.20, 'top': 0.94},
            size_hint=(0.5, 0.24), halign='left', valign='middle',
            text_size=(None, None),
        ))

        # Titre — Sora (headline)
        self.add_widget(Label(
            text=self.event.title,
            font_name=_f.FONT_DISPLAY, font_size=dp(15), bold=True,
            color=theme_manager.get_color("text"),
            pos_hint={'x': 0.20, 'center_y': 0.52},
            size_hint=(0.52, 0.34), halign='left', valign='middle',
            shorten=True, shorten_from='right',
        ))

        # Description — mono discret
        desc = self.event.description or "—"
        if len(desc) > 30:
            desc = desc[:30] + "…"
        self.add_widget(Label(
            text=desc,
            font_name=_f.FONT_MONO, font_size=dp(10),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'x': 0.20, 'y': 0.08},
            size_hint=(0.52, 0.26), halign='left', valign='middle',
        ))

        # Temps restant — mono, accent
        self.add_widget(Label(
            text=self.event.time_until,
            font_name=_f.FONT_MONO, font_size=dp(10),
            color=theme_manager.get_color("accent"),
            pos_hint={'right': 0.88, 'center_y': 0.5},
            size_hint=(0.20, 0.3), halign='right', valign='middle',
        ))

        # Bouton supprimer — il manquait, on ne pouvait pas retirer un rdv
        from nova.ui.widgets import NeonButton
        del_btn = NeonButton(
            icon="delete", accent="error",
            size_hint=(None, None), size=(dp(44), dp(44)),  # zone tactile au poignet
            pos_hint={'right': 0.975, 'center_y': 0.5},
            corner_radius=dp(2),
        )
        del_btn.bind(on_press=lambda *_a: self._confirm_delete())
        self.add_widget(del_btn)

    def _confirm_delete(self):
        """Demande confirmation avant de supprimer l'événement."""
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from nova.ui.widgets import NeonButton

        box = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(14))
        box.add_widget(Label(
            text="Supprimer « {} » ?".format(self.event.title),
            color=theme_manager.get_color("text"),
        ))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        popup = Popup(title="CONFIRMER", content=box,
                      size_hint=(0.7, 0.4), separator_height=dp(1))

        annuler = NeonButton(text="ANNULER", corner_radius=dp(2))
        annuler.bind(on_press=lambda *_a: popup.dismiss())
        supprimer = NeonButton(text="SUPPRIMER", accent="error", corner_radius=dp(2))

        def _do(*_a):
            popup.dismiss()
            if self.on_delete:
                self.on_delete(self.event)
        supprimer.bind(on_press=_do)

        row.add_widget(annuler)
        row.add_widget(supprimer)
        box.add_widget(row)
        popup.open()

    def _refresh_accent(self, *_args):
        """Barre d'accent collée au bord gauche de la carte."""
        if hasattr(self, "_accent_bar"):
            self._accent_bar.pos = (self.x, self.y + dp(6))
            self._accent_bar.size = (dp(3), max(1, self.height - dp(12)))


class AddEventPopup(Popup):
    """Popup d'ajout d'événement."""

    def __init__(self, on_save, **kwargs):
        self.on_save = on_save
        super().__init__(
            title="Nouvel événement",
            size_hint=(0.9, 0.7),
            background_color=(0.05, 0.05, 0.08, 0.95),
            **kwargs
        )
        self._build()

    def _build(self):
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))

        # Titre
        self.title_input = TextInput(
            hint_text="Titre de l'événement",
            multiline=False,
            size_hint_y=None, height=dp(45)
        )
        layout.add_widget(self.title_input)

        # Date
        now = datetime.now()
        self.date_input = TextInput(
            text=now.strftime("%Y-%m-%d"),
            hint_text="Date (YYYY-MM-DD)",
            multiline=False,
            size_hint_y=None, height=dp(40)
        )
        layout.add_widget(self.date_input)

        # Heure
        self.time_input = TextInput(
            text=now.strftime("%H:%M"),
            hint_text="Heure (HH:MM)",
            multiline=False,
            size_hint_y=None, height=dp(40)
        )
        layout.add_widget(self.time_input)

        # Description
        self.desc_input = TextInput(
            hint_text="Description (optionnel)",
            multiline=True,
            size_hint_y=None, height=dp(80)
        )
        layout.add_widget(self.desc_input)

        # Boutons
        btn_layout = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))

        cancel_btn = Button(text="Annuler", on_press=self.dismiss)
        btn_layout.add_widget(cancel_btn)

        save_btn = Button(text="Enregistrer", on_press=self._save)
        btn_layout.add_widget(save_btn)

        layout.add_widget(btn_layout)
        self.add_widget(layout)

    def _save(self, instance):
        event = Event(
            title=self.title_input.text,
            event_date=self.date_input.text,
            event_time=self.time_input.text,
            description=self.desc_input.text,
            priority=2
        )
        self.on_save(event)
        self.dismiss()


class CalendarApp(BaseApp):
    """Application Calendrier complète."""

    app_name = "Agenda"
    app_icon = "event_note"
    app_id = "calendar"

    def __init__(self, **kwargs):
        self.db = CalendarDatabase()
        self.current_date = datetime.now()
        super().__init__(**kwargs)
        Clock.schedule_interval(self._refresh, 60)

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ─── HEADER NAVIGATION ─────────────────────────────────────
        header = BoxLayout(
            size_hint=(0.95, None), height=dp(50),
            pos_hint={'center_x': 0.5, 'top': 0.92}, spacing=dp(8)
        )

        prev_btn = NeonButton(icon="chevron_left", size_hint=(None, 1),
                              width=dp(48), corner_radius=dp(2))
        prev_btn.bind(on_press=lambda x: self._change_day(-1))
        header.add_widget(prev_btn)

        from nova import fonts as _f
        # La date occupe l'espace restant, centree entre les fleches
        self.date_label = Label(
            text=self._format_date(self.current_date),
            font_name=_f.FONT_MONO, font_size=dp(13),
            color=theme_manager.get_color("primary"),
            size_hint=(1, 1), halign='center', valign='middle',
        )
        header.add_widget(self.date_label)

        next_btn = NeonButton(icon="chevron_right", size_hint=(None, 1),
                              width=dp(48), corner_radius=dp(2))
        next_btn.bind(on_press=lambda x: self._change_day(1))
        header.add_widget(next_btn)

        # Charte : libelles de boutons en majuscules (« commandes »)
        add_btn = NeonButton(icon="+", text="NOUVEAU", size_hint=(None, 1),
                             width=dp(120), corner_radius=dp(2))
        add_btn.bind(on_press=self._show_add)
        header.add_widget(add_btn)

        main.add_widget(header)

        # ─── LISTE ÉVÉNEMENTS ──────────────────────────────────────
        scroll = ScrollView(
            size_hint=(0.95, 0.78),
            pos_hint={'center_x': 0.5, 'y': 0.02}
        )

        self.events_layout = BoxLayout(
            orientation='vertical', spacing=dp(8),
            size_hint_y=None, padding=dp(5)
        )
        self.events_layout.bind(minimum_height=self.events_layout.setter('height'))

        scroll.add_widget(self.events_layout)
        main.add_widget(scroll)

        self._load_events()

    def _format_date(self, date):
        jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        mois = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        return f"{jours[date.weekday()]} {date.day} {mois[date.month]}".upper()

    def _change_day(self, delta):
        self.current_date += timedelta(days=delta)
        self.date_label.text = self._format_date(self.current_date)
        self._load_events()

    def _load_events(self):
        self.events_layout.clear_widgets()

        date_str = self.current_date.strftime("%Y-%m-%d")
        events = self.db.get_by_date(date_str)

        if not events:
            self.events_layout.add_widget(Label(
                text="Aucun événement",
                font_size=dp(16),
                color=theme_manager.get_color("text_secondary"),
                size_hint_y=None, height=dp(50)
            ))
            return

        for event in events:
            card = EventCard(event, on_delete=self._delete_event)
            self.events_layout.add_widget(card)

    def _show_add(self, instance):
        popup = AddEventPopup(on_save=self._add_event)
        popup.open()

    def _add_event(self, event):
        self.db.create(event)
        self._load_events()
        print(f"[calendar] Événement ajouté : {event.title}")

    def _delete_event(self, event):
        self.db.delete(event.id)
        self._load_events()

    def _refresh(self, dt=None):
        self._load_events()


NovaApp = CalendarApp
