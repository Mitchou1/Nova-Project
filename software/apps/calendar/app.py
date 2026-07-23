#!/usr/bin/env python3
"""Application Agenda."""

from datetime import datetime, timedelta

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from apps.base_app import BaseApp
from apps.calendar import storage
from nova.ui.theme import theme_manager

PRIORITY_COLORS = {1: "success", 2: "warning", 3: "error"}


class CalendarApp(BaseApp):
    app_name = "Agenda"
    app_icon = "📅"
    app_id = "calendar"

    def __init__(self, **kwargs):
        storage.init_db()
        super().__init__(**kwargs)
        self._reminder_event = Clock.schedule_interval(self.check_reminders, 60)

    def build_ui(self):
        super().build_ui()

        add_button = Button(
            text="+ Nouvel evenement", size_hint_y=0.14, font_size=17,
            background_normal="", background_color=theme_manager.get_color("success"),
        )
        add_button.bind(on_press=self.open_add_dialog)
        self.content.add_widget(add_button)

        scroll = ScrollView()
        self.events_list = GridLayout(cols=1, spacing=8, size_hint_y=None, padding=[0, 6])
        self.events_list.bind(minimum_height=self.events_list.setter("height"))
        scroll.add_widget(self.events_list)
        self.content.add_widget(scroll)

        self.load_events()

    # --- affichage -------------------------------------------------------
    def on_pre_enter(self, *_):
        self.load_events()

    def load_events(self):
        self.events_list.clear_widgets()
        events = storage.get_today_events()

        if not events:
            empty = Label(
                text="Aucun evenement aujourd'hui", font_size=16,
                size_hint_y=None, height=50,
                color=theme_manager.get_color("text_secondary"),
            )
            self.events_list.add_widget(empty)
            return

        for event in events:
            self.events_list.add_widget(self.build_card(event))

    def build_card(self, event):
        card = BoxLayout(size_hint_y=None, height=56, spacing=8)

        card.add_widget(Label(
            text=event["event_time"], font_size=17, bold=True, size_hint_x=0.20,
            color=theme_manager.get_color("primary"),
        ))

        title = Label(text=event["title"], font_size=16, size_hint_x=0.55, halign="left")
        title.bind(size=lambda widget, _v: setattr(widget, "text_size", widget.size))
        card.add_widget(title)

        color_key = PRIORITY_COLORS.get(event["priority"], "text_secondary")
        card.add_widget(Label(
            text="●", font_size=22, size_hint_x=0.10,
            color=theme_manager.get_color(color_key),
        ))

        delete = Button(
            text="X", size_hint_x=0.15, font_size=15, background_normal="",
            background_color=theme_manager.get_color("surface"),
        )
        delete.bind(on_press=lambda _w, eid=event["id"]: self.remove_event(eid))
        card.add_widget(delete)

        return card

    # --- actions ---------------------------------------------------------
    def open_add_dialog(self, *_):
        layout = BoxLayout(orientation="vertical", spacing=8, padding=10)

        title_input = TextInput(hint_text="Titre", multiline=False, size_hint_y=0.25)
        default_time = (datetime.now() + timedelta(hours=1)).strftime("%H:%M")
        time_input = TextInput(text=default_time, multiline=False, size_hint_y=0.25)

        layout.add_widget(title_input)
        layout.add_widget(Label(text="Heure (HH:MM)", size_hint_y=0.15, font_size=13))
        layout.add_widget(time_input)

        buttons = BoxLayout(size_hint_y=0.35, spacing=8)
        popup = Popup(title="Nouvel evenement", content=layout, size_hint=(0.8, 0.6))

        cancel = Button(text="Annuler")
        cancel.bind(on_press=popup.dismiss)

        confirm = Button(text="Ajouter", background_normal="",
                         background_color=theme_manager.get_color("success"))

        def do_add(*_args):
            title = title_input.text.strip() or "Evenement"
            time_value = time_input.text.strip() or default_time
            storage.add_event(
                title=title,
                date=datetime.now().strftime("%Y-%m-%d"),
                time=time_value,
                priority=1,
            )
            popup.dismiss()
            self.load_events()

        confirm.bind(on_press=do_add)
        buttons.add_widget(cancel)
        buttons.add_widget(confirm)
        layout.add_widget(buttons)

        popup.open()

    def remove_event(self, event_id):
        storage.delete_event(event_id)
        self.load_events()

    def check_reminders(self, dt=None):
        for event in storage.due_reminders():
            print("[agenda] RAPPEL : {} a {}".format(event["title"], event["event_time"]))

    def on_cleanup(self):
        if getattr(self, "_reminder_event", None) is not None:
            self._reminder_event.cancel()


NovaApp = CalendarApp
