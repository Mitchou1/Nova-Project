#!/usr/bin/env python3
"""
Grille d'applications NOVA
"""

from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle

class AppButton(Button):
    """Bouton d'application stylisé"""

    def __init__(self, app_id, app_name, app_icon, **kwargs):
        self.app_id = app_id
        super().__init__(
            text=f"{app_icon}\n{app_name}",
            font_size=16,
            halign='center',
            valign='middle',
            background_normal='',
            background_color=(0.15, 0.15, 0.2, 1),
            **kwargs
        )
        self.bind(size=self.update_rect, pos=self.update_rect)
        with self.canvas.before:
            Color(0.2, 0.2, 0.3, 1)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])

    def update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

class AppGrid(GridLayout):
    """Grille des applications sur l'écran d'accueil"""

    def __init__(self, **kwargs):
        super().__init__(
            cols=3,
            spacing=15,
            padding=20,
            size_hint_y=0.6,
            **kwargs
        )
        self.apps = []

    def populate(self, apps_info):
        """Remplit la grille avec les applications"""
        self.clear_widgets()
        self.apps = apps_info

        for app in apps_info:
            btn = AppButton(
                app_id=app['id'],
                app_name=app['name'],
                app_icon=app.get('icon', '📱')
            )
            btn.bind(on_press=self.on_app_press)
            self.add_widget(btn)

    def on_app_press(self, instance):
        """Gère le clic sur une application"""
        print(f"Lancement de l'app : {instance.app_id}")
        # TODO: Intégrer avec le launcher
        # from nova.launcher import launcher
        # launcher.launch_app(instance.app_id)
