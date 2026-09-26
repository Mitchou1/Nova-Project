#!/usr/bin/env python3
"""
App Assistant NOVA — Interface IA vocale.
Pipeline reel : Whisper (faster-whisper) -> Qwen2.5 (llama.cpp) -> Piper.
"""

import threading

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivy.animation import Animation
from kivy.properties import StringProperty, BooleanProperty

from apps.base_app import BaseApp, CIBLE_MIN, haut_contenu, hauteur_relative
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

        # Libellé de l'émetteur — label-caps, aligné à gauche au-dessus du
        # texte (sans text_size, halign était ignoré : libellé décalé)
        emetteur = Label(
            text=" ".join(libelle),          # letter-spacing simulé
            font_name=_f.FONT_MONO, font_size=dp(8),
            color=accent,
            size_hint=(None, None), height=dp(14),
            halign='left', valign='middle',
        )
        self._emetteur = emetteur
        self.add_widget(emetteur)

        # Texte — aligné à gauche. La bulle prend la hauteur RÉELLE du texte
        # rendu (retours à la ligne compris) et la suit mot à mot pendant la
        # réponse en direct. Avant : hauteur estimée une fois pour toutes
        # (1 ligne / 60 caractères), et une bulle de réponse créée vide
        # restait à une seule ligne -> le texte débordait de la bulle.
        self.text_label = Label(
            text=text,
            font_name=_f.FONT_DISPLAY, font_size=dp(13),
            color=theme_manager.get_color("text"),
            size_hint=(None, None),
            halign='left', valign='top',
        )
        self.text_label.bind(texture_size=self._ajuster_hauteur)
        self.bind(pos=self._placer_texte, size=self._placer_texte)
        self.add_widget(self.text_label)

    MARGE_HAUT = dp(22)       # place du libellé « NOVA » / « VOUS »
    MARGE_BAS = dp(8)

    def _placer_texte(self, *_a):
        em = self._emetteur
        em.width = self.width * 0.93
        em.text_size = (em.width, em.height)
        em.pos = (self.x + self.width * 0.035, self.top - dp(4) - em.height)
        lbl = self.text_label
        lbl.width = self.width * 0.93
        lbl.text_size = (lbl.width, None)     # largeur fixe, hauteur libre
        lbl.pos = (self.x + self.width * 0.035, self.y + self.MARGE_BAS)

    def _ajuster_hauteur(self, *_a):
        hauteur_texte = max(self.text_label.texture_size[1], dp(16))
        self.text_label.height = hauteur_texte
        self.height = hauteur_texte + self.MARGE_HAUT + self.MARGE_BAS
        self._placer_texte()

    def _refresh_accent(self, *_args):
        if hasattr(self, "_accent_bar"):
            self._accent_bar.pos = (self.x, self.y + dp(5))
            self._accent_bar.size = (dp(3), max(1, self.height - dp(10)))


class AssistantApp(BaseApp):
    """Application Assistant IA — interface complète."""

    HAUTEUR_PANNEAU = dp(150)     # panneau vocal (micro + saisie), en bas

    app_name = "NOVA"
    app_icon = "smart_toy"
    app_id = "assistant"

    is_listening = BooleanProperty(False)
    status_text = StringProperty("Appuyez et parlez")

    def __init__(self, **kwargs):
        # Historique conversation (audit : etait un attribut de CLASSE,
        # partage entre toutes les instances au lieu d'etre propre a
        # chacune). Doit etre pose AVANT super().__init__() : BaseApp.__init__
        # appelle self.build_ui(), qui affiche le message de bienvenue via
        # _add_message(), qui lit self.conversation — sinon AttributeError
        # des la construction de l'ecran (bug reel observe au lancement).
        self.conversation = []
        # Moteur IA : chargement PARESSEUX (audit, severite HAUTE) — charger
        # Whisper + le LLM (~2,4 Go) + Piper de facon synchrone ici figeait
        # toute l'application au demarrage, AVANT meme l'affichage de la
        # fenetre (AppLauncher instancie toutes les apps sur le thread
        # principal Kivy pendant App.build()). Le moteur ne se charge donc
        # plus qu'au premier usage reel, dans _get_engine() — appele depuis
        # _run_pipeline/_run_typed_pipeline qui tournent deja dans un thread
        # separe, jamais sur le thread UI.
        self._engine = None
        self._engine_lock = threading.Lock()
        self._last_audio = None
        # Audit (crash reel observe, severite CRITIQUE) : appuyer sur le
        # micro pendant qu'une reponse precedente etait encore en train
        # d'etre lue a voix haute lancait un DEUXIEME thread accedant a la
        # carte son (sd.rec) en meme temps que le premier (sd.play) ->
        # corruption memoire native de PortAudio, crash total de l'appli
        # ("free(): invalid size", SIGABRT). Empeche desormais de demarrer
        # un second pipeline (vocal ou texte) tant qu'un premier n'est pas
        # termine — en complement du verrou bas niveau dans ai_engine.py.
        self._pipeline_busy = False
        super().__init__(**kwargs)

    def _get_engine(self):
        """Charge le moteur IA au premier appel reel (voir __init__).

        Verrou : appelee depuis les threads du pipeline vocal et du pipeline
        texte, qui peuvent demarrer quasi simultanement (micro + saisie
        rapide) — sans lui, les deux threads passaient le test self._engine
        is None avant qu'aucun n'affecte la variable.
        """
        if self._engine is None:
            with self._engine_lock:
                if self._engine is None:
                    from kivy.clock import Clock
                    Clock.schedule_once(
                        lambda dt: self._set_status("Chargement du modèle IA..."), 0)
                    from nova.ai_engine import get_engine
                    moteur = get_engine()
                    self._engine = moteur
                    if moteur.fully_simulated():
                        # Audit (severite HAUTE) : un echec de chargement (modele
                        # manquant, OOM, fichier corrompu) tombait en simulation
                        # sans jamais le signaler — un print() seul est invisible
                        # sur un wearable sans terminal.
                        Clock.schedule_once(lambda dt: self._add_message(
                            "⚠ Modèle IA indisponible — je réponds en mode simulation.",
                            is_user=False), 0)
        return self._engine

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

        # Conversation : de l'en-tête jusqu'au-dessus du panneau vocal. Avant,
        # elle descendait DERRIÈRE ce panneau (bulles cachées par le micro).
        haut = haut_contenu()
        bas_conversation = 0.02 + hauteur_relative(self.HAUTEUR_PANNEAU + dp(8))
        scroll = ScrollView(
            size_hint=(1, haut - bas_conversation),
            pos_hint={'x': 0, 'top': haut}
        )
        scroll.add_widget(self.chat_container)
        self.chat_scroll = scroll
        # La conversation grandit (nouvelle bulle, ou réponse qui s'allonge
        # mot à mot) : on reste calé sur le dernier message.
        self.chat_container.bind(height=lambda *_a: setattr(scroll, "scroll_y", 0))
        main.add_widget(scroll)

        # Message de bienvenue
        self._add_message("Bonjour ! Je suis NOVA, votre assistant personnel. Comment puis-je vous aider ?", is_user=False)

        # ─── ZONE CONTRÔLE ─────────────────────────────────────────
        # Panneau compact (230 -> 150 px) : il occupait près de la moitié de
        # l'écran. Du bas vers le haut : saisie (44 px), statut, micro (56 px),
        # onde sonore.
        control_card = GlassCard(
            size_hint=(0.95, None),
            height=self.HAUTEUR_PANNEAU,
            pos_hint={'center_x': 0.5, 'y': 0.02},
            corner_radius=dp(2)
        )

        # Visualiseur d'onde
        self.waveform = WaveformVisualizer(
            size_hint=(0.8, None),
            height=dp(20),
            pos_hint={'center_x': 0.5, 'top': 0.98},
            bar_count=20,
            amplitude=0.2
        )
        control_card.add_widget(self.waveform)

        # Statut — placé SOUS le bouton rond (il se superposait dessus)
        self.status_label = Label(
            text=self.status_text,
            font_size=dp(12),
            color=theme_manager.get_color("text_secondary"),
            pos_hint={'center_x': 0.5, 'y': 0.34},
            size_hint=(0.9, 0.12),
            halign='center', valign='middle',
        )
        control_card.add_widget(self.status_label)

        # Bouton principal
        # Icône seule : à 56 px, « PARLER » se coupait en deux lignes ; le
        # statut juste en dessous (« Appuyez et parlez ») suffit.
        self.talk_btn = NeonButton(
            icon="mic",
            size_hint=(None, None),
            size=(dp(56), dp(56)),
            pos_hint={'center_x': 0.5, 'y': 0.47},
            corner_radius=dp(28)
        )
        self.talk_btn.bind(on_press=self._on_talk_press)
        self.talk_btn.bind(on_release=self._on_talk_release)
        control_card.add_widget(self.talk_btn)

        # ─── CHAMP DE SAISIE TEXTE (pour taper les commandes) ─────
        input_row = BoxLayout(
            size_hint=(0.9, None), height=CIBLE_MIN, spacing=dp(6),   # cible tactile >= 44 px
            pos_hint={'center_x': 0.5, 'y': 0.03}
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
                              width=dp(48), corner_radius=dp(2))
        send_btn.bind(on_press=self._on_text_send)
        input_row.add_widget(send_btn)
        control_card.add_widget(input_row)

        main.add_widget(control_card)

    def _on_text_send(self, instance):
        """Envoie la commande tapée au clavier (sans passer par la voix)."""
        text = self.text_input.text.strip()
        if not text:
            return
        if self._pipeline_busy:
            # Une reponse (vocale ou texte) est deja en cours : ignorer plutot
            # que de lancer un deuxieme thread concurrent sur la carte son.
            self._set_status("Patientez, je traite deja une demande...")
            return
        self._pipeline_busy = True
        self.text_input.text = ""
        print("[assistant] Tape (texte) : {!r}".format(text))
        # réutilise le même pipeline, mais avec le vrai texte tapé
        self._last_typed = text
        import threading
        threading.Thread(target=self._run_typed_pipeline, args=(text,),
                         daemon=True).start()

    def _run_typed_pipeline(self, user_text):
        """Traite une commande TAPÉE : texte -> réponse -> (action)."""
        from kivy.clock import Clock
        try:
            engine = self._get_engine()
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
        finally:
            # Toujours relacher, meme si respond()/say() a leve une exception.
            self._pipeline_busy = False

    def _add_message(self, text, is_user=False):
        """Ajoute un message à la conversation. Renvoie le Label (pour maj)."""
        # La bulle calcule elle-même sa hauteur d'après le texte rendu
        bubble = ChatBubble(text, is_user)

        self.chat_container.add_widget(bubble)
        self.conversation.append({"text": text, "is_user": is_user})
        return bubble.text_label

    def _on_talk_press(self, instance):
        """Début de l'écoute."""
        if self._pipeline_busy:
            # Une reponse est deja en cours (voix ou texte) : ignorer cet
            # appui plutot que de risquer un enregistrement concurrent a
            # une lecture TTS en cours (cf. audit crash dans __init__).
            self._set_status("Patientez, je traite deja une demande...")
            return
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
        if not self.is_listening:
            # L'appui avait ete ignore par _on_talk_press (pipeline deja
            # occupe) : ne pas lancer de deuxieme thread au relachement.
            return
        self.is_listening = False
        # Réduire amplitude
        self.waveform.amplitude = 0.2
        # Animation retour bouton
        from kivy.metrics import dp
        Animation.cancel_all(self.talk_btn, "press_inset")
        Animation(press_inset=0, duration=0.25, t="out_elastic").start(self.talk_btn)
        # Lancer la chaîne dans un thread pour ne pas figer l'interface
        self._pipeline_busy = True
        import threading
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self):
        """Chaîne complète : écoute micro → Whisper → Qwen → (action)."""
        from kivy.clock import Clock
        try:
            engine = self._get_engine()

            # 1) Écoute + transcription (audio -> texte)
            # Whisper enregistre lui-même 5s depuis le micro puis transcrit.
            Clock.schedule_once(lambda dt: self._set_status("Écoute... parlez"), 0)
            user_text = engine.transcribe(None)  # None = enregistre depuis le micro
            # Audit : jamais logue nulle part -> impossible de diagnostiquer une
            # commande vocale mal reconnue sans capture d'ecran (le texte n'etait
            # visible que dans l'UI, pas en console).
            print("[assistant] Transcrit (voix) : {!r}".format(user_text))

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
        finally:
            # Toujours relacher, meme si transcribe()/respond()/say() a leve
            # une exception — sinon le pipeline reste bloque "busy" a vie.
            self._pipeline_busy = False

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
