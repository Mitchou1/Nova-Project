#!/usr/bin/env python3
"""
App Assistant NOVA — Interface IA vocale.
Pipeline reel : Whisper (faster-whisper) -> Qwen2.5 (llama.cpp) -> Piper.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivy.animation import Animation
from kivy.properties import StringProperty, BooleanProperty

from apps.base_app import BaseApp
from nova.ui.theme import theme_manager
from nova.ui.widgets import GlassCard, NeonButton, WaveformVisualizer



def _underline(widget):
    """Trace un filet sous un champ de saisie (charte : underlined inputs).

    Le filet s'illumine en couleur primaire quand le champ a le focus.
    """
    from kivy.graphics import Color, Rectangle

    with widget.canvas.after:
        col = Color(*theme_manager.get_with_alpha("text_secondary", 0.45))
        rect = Rectangle()

    def _place(*_a):
        rect.pos = (widget.x, widget.y + dp(2))
        rect.size = (widget.width, dp(1.4))

    def _focus(_w, actif):
        col.rgba = (theme_manager.get_color("primary") if actif
                    else theme_manager.get_with_alpha("text_secondary", 0.45))

    widget.bind(pos=_place, size=_place, focus=_focus)
    _place()
    return rect


class ChatBubble(GlassCard):
    """Bulle de conversation — charte NOVA (Stitch).

    Barre d'accent latérale, libellé en label-caps identifiant l'émetteur,
    texte en Sora aligné à gauche.
    """

    def __init__(self, text, is_user=False, **kwargs):
        super().__init__(
            size_hint=(0.86, None),
            height=dp(58),
            corner_radius=dp(2),
            chamfer=dp(8),
            **kwargs
        )
        from nova import fonts as _f
        from kivy.graphics import Color, Rectangle

        self.is_user = is_user

        # Couleur et côté selon l'émetteur
        if is_user:
            self.bg_color.rgba = theme_manager.get_with_alpha("surface_light", 0.6)
            accent = theme_manager.get_color("text_secondary")
            self.pos_hint = {'right': 0.98}
            libelle = "VOUS"
        else:
            self.bg_color.rgba = theme_manager.get_with_alpha("primary", 0.12)
            accent = theme_manager.get_color("primary")
            self.pos_hint = {'x': 0.02}
            libelle = "NOVA"

        # Barre d'accent verticale (comme la carte événement de la maquette)
        with self.canvas.after:
            self._accent_color = Color(*accent)
            self._accent_bar = Rectangle()
        self.bind(pos=self._refresh_accent, size=self._refresh_accent)

        # Libellé de l'émetteur — label-caps
        self.add_widget(Label(
            text=" ".join(libelle),          # letter-spacing simulé
            font_name=_f.FONT_MONO, font_size=dp(8),
            color=accent,
            pos_hint={'x': 0.035, 'top': 0.95},
            size_hint=(0.4, 0.26),
            halign='left', valign='middle',
        ))

        # Texte — aligné à gauche (il était centré, d'où un rendu bancal)
        self.text_label = Label(
            text=text,
            font_name=_f.FONT_DISPLAY, font_size=dp(13),
            color=theme_manager.get_color("text"),
            pos_hint={'x': 0.035, 'y': 0.06},
            size_hint=(0.93, 0.62),
            halign='left', valign='top',
        )
        self.text_label.bind(
            size=lambda w, s: setattr(w, "text_size", (s[0], s[1])))
        self.add_widget(self.text_label)

    def _refresh_accent(self, *_args):
        if hasattr(self, "_accent_bar"):
            self._accent_bar.pos = (self.x, self.y + dp(5))
            self._accent_bar.size = (dp(3), max(1, self.height - dp(10)))


class AssistantApp(BaseApp):
    """Application Assistant IA — interface complète."""

    app_name = "NOVA"
    app_icon = "smart_toy"
    app_id = "assistant"

    is_listening = BooleanProperty(False)
    status_text = StringProperty("Appuyez et parlez")

    # Historique conversation
    conversation = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Moteur IA (chaîne parole → texte → réponse → voix)
        from nova.ai_engine import get_engine
        self._engine = get_engine()
        self._last_audio = None

    def build_ui(self):
        super().build_ui()
        main = self.children[0]

        # ─── ZONE CONVERSATION ─────────────────────────────────────
        self.chat_container = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=dp(8),
            padding=dp(10)
        )
        self.chat_container.bind(
            minimum_height=self.chat_container.setter('height')
        )

        scroll = ScrollView(
            size_hint=(1, 0.65),
            pos_hint={'x': 0, 'top': 0.88}
        )
        scroll.add_widget(self.chat_container)
        main.add_widget(scroll)

        # Message de bienvenue
        self._add_message("Bonjour ! Je suis NOVA, votre assistant personnel. Comment puis-je vous aider ?", is_user=False)

        # ─── ZONE CONTRÔLE ─────────────────────────────────────────
        control_card = GlassCard(
            size_hint=(0.95, None),
            height=dp(230),
            pos_hint={'center_x': 0.5, 'y': 0.02},
            corner_radius=dp(2)
        )

        # Visualiseur d'onde
        self.waveform = WaveformVisualizer(
            size_hint=(0.8, None),
            height=dp(40),
            pos_hint={'center_x': 0.5, 'top': 0.85},
            bar_count=20,
            amplitude=0.2
        )
        control_card.add_widget(self.waveform)

        # Statut — placé SOUS le bouton rond (il se superposait dessus)
        self.status_label = Label(
            text=self.status_text,
            font_size=dp(12),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'center_x': 0.5, 'top': 0.30},
            size_hint=(0.9, 0.10),
            halign='center', valign='middle',
        )
        control_card.add_widget(self.status_label)

        # Bouton principal
        self.talk_btn = NeonButton(
            icon="mic",
            text="Parler",
            size_hint=(None, None),
            size=(dp(70), dp(70)),
            pos_hint={'center_x': 0.5, 'y': 0.32},
            corner_radius=dp(35)
        )
        self.talk_btn.bind(on_press=self._on_talk_press)
        self.talk_btn.bind(on_release=self._on_talk_release)
        control_card.add_widget(self.talk_btn)

        # ─── CHAMP DE SAISIE TEXTE (pour taper les commandes) ─────
        input_row = BoxLayout(
            size_hint=(0.9, None), height=dp(38), spacing=dp(6),
            pos_hint={'center_x': 0.5, 'y': 0.04}
        )
        from nova import fonts as _f
        # Charte NOVA : "underlined inputs" — pas de boite, juste un filet
        # sous le texte, qui s'illumine quand le champ a le focus.
        self.text_input = TextInput(
            hint_text="ÉCRIRE UNE COMMANDE...",
            multiline=False, size_hint=(1, 1),
            font_name=_f.FONT_MONO, font_size=dp(12),
            padding=[dp(4), dp(10)],
            background_color=(0, 0, 0, 0),          # transparent
            foreground_color=theme_manager.get_color("text"),
            hint_text_color=theme_manager.get_with_alpha("text_secondary", 0.55),
            cursor_color=theme_manager.get_color("primary"),
        )
        self.text_input.bind(on_text_validate=self._on_text_send)
        _underline(self.text_input)
        input_row.add_widget(self.text_input)

        send_btn = NeonButton(icon="chevron_right", size_hint=(None, 1),
                              width=dp(44), corner_radius=dp(2))
        send_btn.bind(on_press=self._on_text_send)
        input_row.add_widget(send_btn)
        control_card.add_widget(input_row)

        main.add_widget(control_card)

    def _on_text_send(self, instance):
        """Envoie la commande tapée au clavier (sans passer par la voix)."""
        text = self.text_input.text.strip()
        if not text:
            return
        self.text_input.text = ""
        # réutilise le même pipeline, mais avec le vrai texte tapé
        self._last_typed = text
        import threading
        threading.Thread(target=self._run_typed_pipeline, args=(text,),
                         daemon=True).start()

    def _run_typed_pipeline(self, user_text):
        """Traite une commande TAPÉE : texte -> réponse -> (action)."""
        from kivy.clock import Clock
        engine = self._engine
        # Afficher le message de l'utilisateur
        Clock.schedule_once(lambda dt: self._add_message(user_text, is_user=True), 0)
        Clock.schedule_once(lambda dt: self._set_status("Réflexion..."), 0)
        # Bulle de réponse
        holder = {"label": None, "text": ""}
        Clock.schedule_once(lambda dt: holder.__setitem__("label",
                            self._add_message("", is_user=False)), 0)

        def on_token(piece):
            holder["text"] += piece
            lbl = holder["label"]
            if lbl is not None:
                Clock.schedule_once(
                    lambda dt, t=holder["text"]: self._update_bubble(lbl, t), 0)

        reply = engine.respond(user_text, on_token=on_token, app=self)
        # NOVA lit sa réponse à voix haute (Piper)
        if reply:
            engine.say(reply)
        Clock.schedule_once(lambda dt: self._set_status("Prêt", idle=True), 0)

    def _add_message(self, text, is_user=False):
        """Ajoute un message à la conversation. Renvoie le Label (pour maj)."""
        bubble = ChatBubble(text, is_user)

        # Ajuster la hauteur selon le texte (place pour le libelle emetteur
        # en label-caps + les lignes du message)
        lignes = max(1, len(text) // 60 + 1)
        bubble.height = dp(34 + lignes * 19)

        self.chat_container.add_widget(bubble)
        self.conversation.append({"text": text, "is_user": is_user})
        return bubble.text_label

    def _on_talk_press(self, instance):
        """Début de l'écoute."""
        self.is_listening = True
        self.status_text = "Écoute en cours..."
        self.status_label.text = self.status_text
        self.status_label.color = theme_manager.get_color("primary")

        # Animer le bouton (press_inset existe sur NeonButton via GlassCard)
        from kivy.metrics import dp
        Animation.cancel_all(self.talk_btn, "press_inset")
        Animation(press_inset=dp(4), duration=0.2, t="out_quad").start(self.talk_btn)

        # Augmenter l'amplitude du visualiseur
        self.waveform.amplitude = 0.8

        print("[assistant] Ecoute demarree")

    def _on_talk_release(self, instance):
        """Fin de l'appui — lance la chaîne écoute → texte → réponse."""
        self.is_listening = False
        # Réduire amplitude
        self.waveform.amplitude = 0.2
        # Animation retour bouton
        from kivy.metrics import dp
        Animation.cancel_all(self.talk_btn, "press_inset")
        Animation(press_inset=0, duration=0.25, t="out_elastic").start(self.talk_btn)
        # Lancer la chaîne dans un thread pour ne pas figer l'interface
        import threading
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self):
        """Chaîne complète : écoute micro → Whisper → Qwen → (action)."""
        from kivy.clock import Clock
        engine = self._engine

        # 1) Écoute + transcription (audio -> texte)
        # Whisper enregistre lui-même 5s depuis le micro puis transcrit.
        Clock.schedule_once(lambda dt: self._set_status("Écoute... parlez"), 0)
        user_text = engine.transcribe(None)  # None = enregistre depuis le micro

        if not user_text or not user_text.strip():
            Clock.schedule_once(
                lambda dt: self._set_status("Je n'ai rien entendu", idle=True), 0)
            return

        # Afficher ce que l'utilisateur a dit
        Clock.schedule_once(lambda dt: self._add_message(user_text, is_user=True), 0)
        Clock.schedule_once(lambda dt: self._set_status("Réflexion..."), 0)

        # 2) Réponse (texte -> réponse), affichée mot à mot
        holder = {"label": None, "text": ""}

        def start_bubble(dt):
            holder["label"] = self._add_message("", is_user=False)

        Clock.schedule_once(start_bubble, 0)

        def on_token(piece):
            holder["text"] += piece
            lbl = holder["label"]
            if lbl is not None:
                # mettre à jour le texte de la bulle sur le thread graphique
                Clock.schedule_once(
                    lambda dt, t=holder["text"]: self._update_bubble(lbl, t), 0)

        reply = engine.respond(user_text, on_token=on_token, app=self)

        # 3) Voix (texte -> audio)
        engine.say(reply)

        # Revenir à l'état d'attente
        Clock.schedule_once(lambda dt: self._set_status("Appuyez et parlez", idle=True), 0)
        print("[assistant] Reponse : {}".format(reply))

    def _set_status(self, text, idle=False):
        self.status_text = text
        self.status_label.text = text
        self.status_label.color = (
            theme_manager.get_color("text_secondary") if idle
            else theme_manager.get_color("primary"))

    def _update_bubble(self, label, text):
        """Met à jour le texte d'une bulle de réponse existante."""
        try:
            label.text = text
        except Exception:
            pass

NovaApp = AssistantApp
