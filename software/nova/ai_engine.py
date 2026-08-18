#!/usr/bin/env python3
"""Moteur de l'assistant NOVA : parole → texte → réponse → voix.

Trois briques indépendantes et remplaçables :

  - SpeechToText  : audio -> texte      (Whisper plus tard)
  - LanguageModel : texte -> réponse    (llama.cpp / TinyLlama plus tard)
  - TextToSpeech  : texte -> voix        (Piper plus tard)

Par défaut, chaque brique tourne en mode SIMULATION : elle renvoie des données
d'exemple, sans matériel ni modèle. Cela permet de tester toute la chaîne de
l'application (états, affichage, enchaînement) avant d'installer quoi que ce
soit. Quand les vrais modèles seront présents, il suffit de compléter la
méthode réelle de chaque brique — le reste de l'application ne change pas.

Tout est conçu pour fonctionner HORS LIGNE : aucun appel réseau.
"""

import random
import threading
import time
from pathlib import Path

from nova.paths import MODELS_DIR
from nova.utils.platform_utils import is_raspberry_pi

# Verrou partage entre enregistrement (STT) et lecture (TTS) : sounddevice/
# PortAudio n'est pas concu pour deux flux (lecture + enregistrement) ouverts
# simultanement depuis des threads differents sur le meme peripherique. Audit
# (crash reel observe) : appuyer sur le micro (pipeline vocal, nouveau thread)
# PENDANT qu'une reponse precedente etait encore lue a voix haute (pipeline
# texte, thread separe) corrompait la memoire native de PortAudio — plantage
# total de l'application ("free(): invalid size", SIGABRT/IOT). Les deux
# pipelines (vocal et texte) tournent chacun dans leur propre thread
# (apps/assistant/app.py) sans aucune coordination entre eux ; ce verrou est
# donc la seule protection commune aux deux chemins.
_AUDIO_IO_LOCK = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Brique 1 : reconnaissance vocale (Speech To Text)
# ─────────────────────────────────────────────────────────────────────────────
class SpeechToText:
    """Transcrit la voix en texte avec faster-whisper (micro -> texte).

    Si faster-whisper n'est pas installé, retombe sur une simulation
    (phrases d'exemple) pour ne pas bloquer le reste de l'application.
    """

    # Phrases d'exemple si Whisper indisponible (repli)
    _SIMULATED = [
        "Quelle heure est-il ?",
        "Ajoute un rendez-vous demain à quinze heures",
        "Quel est mon prochain événement ?",
        "Passe en mode cyberpunk",
    ]

    SAMPLE_RATE = 16000
    RECORD_SECONDS = 5   # durée d'écoute par défaut

    def __init__(self, model_name=None):
        self.model_name = model_name or self._configured_model_name()
        self.model = None
        self.ready = False
        self._try_load()

    @staticmethod
    def _configured_model_name():
        """Taille du modele Whisper : suit config.ai.whisper_model si
        defini (audit : cette cle existait dans system.json mais etait
        silencieusement ignoree — le code forcait "base" sur Pi quelle que
        soit la config). Sans config explicite, "small" par defaut : cible
        confirmee Raspberry Pi 5 (RAM largement suffisante pour le meme
        modele qu'en dev PC, contrairement au Pi Zero 2W vise a l'origine).
        """
        try:
            from nova.utils.config_loader import get_config
            configure = (get_config().get("ai", {}) or {}).get("whisper_model")
            if configure:
                return configure
        except Exception:
            pass
        return "small"

    def _try_load(self):
        """Charge le modèle Whisper si faster-whisper est disponible."""
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            self.ready = True
            print("[stt] Whisper chargé :", self.model_name)
        except Exception as error:
            print("[stt] Whisper indisponible ({}), mode simulation".format(error))
            self.model = None
            self.ready = False

    def record(self, seconds=None):
        """Enregistre depuis le micro et renvoie les échantillons audio."""
        seconds = seconds or self.RECORD_SECONDS
        try:
            import sounddevice as sd
            # Verrou : ne jamais enregistrer pendant qu'une lecture TTS est en
            # cours sur un autre thread (cf. _AUDIO_IO_LOCK plus haut).
            with _AUDIO_IO_LOCK:
                audio = sd.rec(int(seconds * self.SAMPLE_RATE),
                              samplerate=self.SAMPLE_RATE, channels=1, dtype="float32")
                sd.wait()
            return audio.flatten()
        except Exception as error:
            print("[stt] enregistrement micro impossible :", error)
            return None

    def transcribe(self, audio_data=None):
        """Transcrit l'audio en texte. Si audio_data est None, enregistre d'abord.

        La langue suit la config (language: fr/en/ar) au lieu d'etre figee
        en francais — coherent avec le multilingue de assistant_actions.py.
        """
        if self.ready and self.model is not None:
            if audio_data is None:
                audio_data = self.record()
            if audio_data is None:
                return ""
            try:
                segments, _info = self.model.transcribe(
                    audio_data, language=self._langue_configuree())
                text = "".join(seg.text for seg in segments).strip()
                return text
            except Exception as error:
                print("[stt] transcription impossible :", error)
                return ""
        # Repli simulation
        time.sleep(0.3)
        return random.choice(self._SIMULATED)

    @staticmethod
    def _langue_configuree():
        try:
            from nova.utils.config_loader import get_config
            langue = (get_config().get("language") or "fr").strip().lower()
            return langue if langue in ("fr", "en", "ar") else "fr"
        except Exception:
            return "fr"

    @property
    def simulated(self):
        return not self.ready


# ─────────────────────────────────────────────────────────────────────────────
# Brique 2 : génération de réponse (Language Model)
# ─────────────────────────────────────────────────────────────────────────────
class LanguageModel:
    """Génère une réponse à partir d'un texte. Simulé tant que le LLM est absent.

    La simulation est un peu « intelligente » : elle reconnaît quelques intentions
    simples (heure, salutation, remerciement…) pour que la démo soit crédible,
    et retombe sur une réponse générique sinon.
    """

    def __init__(self, model_file="qwen2.5-3b-instruct-q5_k_m.gguf"):
        self.model_file = model_file
        self.model = None
        self.ready = False
        self._try_load()

    def _model_path(self):
        return MODELS_DIR / "llm" / self.model_file

    def _try_load(self):
        path = self._model_path()
        if not path.exists():
            return  # simulation si le modèle n'est pas présent
        try:
            from llama_cpp import Llama
            from nova.utils.platform_utils import is_raspberry_pi
            # Cible confirmee Raspberry Pi 5 : 4 coeurs physiques (Cortex-A76),
            # comme le Pi Zero 2W vise a l'origine — n_threads=4 reste donc le
            # bon choix ici (un thread par coeur physique ; au-dela, on
            # oversubscrit sans gain reel pour un charge CPU-bound comme
            # l'inference llama.cpp). Seule la taille du modele Whisper
            # (voir SpeechToText._configured_model_name) profite vraiment de
            # la RAM bien plus large du Pi 5 par rapport au Zero 2W.
            n_threads = 4 if is_raspberry_pi() else 8
            self.model = Llama(
                model_path=str(path),
                # Audit : 2048 etait trop juste des que l'historique
                # persistant (memory_store) grossit — plante en usage reel
                # avec "Requested tokens (2060) exceed context window of
                # 2048", puis la reponse suivante devenait imprevisible
                # (echec avale, retombe sur du texte libre sans JSON). Qwen
                # 2.5 3B q5_k_m supporte 4096 sans souci de RAM sur la
                # cible Pi 5 (memes raisons que le choix du modele Whisper).
                n_ctx=4096,
                n_threads=n_threads,
                verbose=False,
            )
            self.ready = True
            print("[llm] modèle chargé :", self.model_file)
        except Exception as error:
            print("[llm] chargement du modèle impossible : {}".format(error))
            self.model = None
            self.ready = False

    # --- simulation d'intentions simples ---------------------------------
    def _simulated_reply(self, text):
        low = text.lower().strip()
        from datetime import datetime

        if any(w in low for w in ("heure", "quelle heure")):
            return "Il est {}.".format(datetime.now().strftime("%H:%M"))
        if any(w in low for w in ("bonjour", "salut", "coucou", "hello")):
            return "Bonjour ! Comment puis-je vous aider ?"
        if any(w in low for w in ("merci", "thanks")):
            return "Avec plaisir."
        if any(w in low for w in ("météo", "temps", "meteo")):
            return ("Je ne peux pas encore consulter la météo hors ligne, "
                    "mais je pourrai le faire avec le bon capteur.")
        if any(w in low for w in ("rendez-vous", "rdv", "événement", "evenement", "agenda")):
            return "Je peux ajouter cela à votre agenda. Quel jour et quelle heure ?"
        if any(w in low for w in ("cyberpunk", "classic", "undercover", "mode")):
            return "Vous pouvez changer de mode avec le bouton palette de l'accueil."
        if "?" in text:
            return ("Bonne question. Une fois le modèle installé, "
                    "je pourrai y répondre vraiment.")
        return random.choice([
            "Je comprends. Souhaitez-vous que je note quelque chose ?",
            "D'accord, je m'en occupe.",
            "Entendu.",
            "Dites m'en un peu plus.",
        ])

    def generate(self, text, on_token=None):
        """Renvoie la réponse complète.

        on_token : fonction optionnelle appelée pour chaque fragment, afin
        d'afficher la réponse au fur et à mesure.
        """
        if self.ready and self.model is not None:
            # Vraie génération avec le modèle local (format chat + streaming)
            system = ("Tu es NOVA, un assistant personnel embarqué. "
                      "Réponds en français, de façon concise et utile.")
            full = ""
            try:
                stream = self.model.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": text},
                    ],
                    max_tokens=256,
                    temperature=0.7,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk["choices"][0].get("delta", {})
                    piece = delta.get("content", "")
                    if piece:
                        full += piece
                        if on_token:
                            on_token(piece)
                return full.strip()
            except Exception as error:
                print("[llm] erreur de génération :", error)
                # bascule sur la simulation en cas de souci
        # Simulation : on « tape » la réponse mot à mot pour l'effet
        reply = self._simulated_reply(text)
        if on_token:
            for word in reply.split(" "):
                on_token(word + " ")
                time.sleep(0.04)
        return reply

    @property
    def simulated(self):
        return not self.ready


# ─────────────────────────────────────────────────────────────────────────────
# Brique 3 : synthèse vocale (Text To Speech)
# ─────────────────────────────────────────────────────────────────────────────
class TextToSpeech:
    """Lit un texte à voix haute avec Piper (synthèse vocale hors ligne).

    Si Piper ou la voix ne sont pas là, reste en simulation (silencieux)
    sans bloquer le reste de l'application.
    """

    def __init__(self, voice="fr_FR-siwis-medium.onnx"):
        self.voice = voice
        self.voice_model = None
        self.ready = False
        self._try_load()

    def _voice_path(self):
        return MODELS_DIR / "tts" / self.voice

    def _try_load(self):
        path = self._voice_path()
        if not path.exists():
            return  # simulation : voix non téléchargée
        try:
            from piper import PiperVoice
            self.voice_model = PiperVoice.load(str(path))
            self.ready = True
            print("[tts] voix chargée :", self.voice)
        except Exception as error:
            print("[tts] chargement de la voix impossible :", error)
            self.voice_model = None
            self.ready = False

    def speak(self, text):
        """Prononce le texte à voix haute via Piper."""
        if self.ready and self.voice_model is not None and text.strip():
            try:
                import sounddevice as sd
                import numpy as np
                chunks = []
                for chunk in self.voice_model.synthesize(text):
                    chunks.append(chunk.audio_int16_array)
                if chunks:
                    audio = np.concatenate(chunks)
                    rate = self.voice_model.config.sample_rate
                    audio, rate = self._adapt_to_output_device(audio, rate)
                    # Verrou : ne jamais lire pendant qu'un enregistrement
                    # micro est en cours sur un autre thread (idem record()).
                    with _AUDIO_IO_LOCK:
                        sd.play(audio, samplerate=rate)
                        sd.wait()
                return True
            except Exception as error:
                print("[tts] synthèse vocale impossible :", error)
                return False
        # Simulation (silencieux, le texte reste affiché à l'écran)
        print("[tts] (simulation) prononce :", text[:60])
        return False

    @staticmethod
    def _adapt_to_output_device(audio, rate):
        """Rééchantillonne l'audio si le peripherique de sortie par defaut
        n'accepte pas le taux natif de la voix Piper (22050 Hz).

        Audit : certains peripheriques (ex. sortie HDMI sans ecran branche,
        choisie par defaut par PulseAudio/ALSA a la place des haut-parleurs)
        rejettent ce taux avec "Invalid sample rate" (PaErrorCode -9997) —
        sd.play() levait alors une exception et aucun son ne sortait jamais,
        meme quand Piper etait correctement charge. On rééchantillonne donc
        toujours vers le taux par defaut reellement rapporte par le
        peripherique de sortie avant lecture (pas de dependance scipy : simple
        interpolation lineaire, suffisante pour de la parole).
        """
        import numpy as np
        import sounddevice as sd
        try:
            device_rate = int(sd.query_devices(kind="output")["default_samplerate"])
        except Exception:
            return audio, rate
        if device_rate <= 0 or device_rate == rate:
            return audio, rate
        duration = len(audio) / float(rate)
        nb_echantillons = max(1, int(round(duration * device_rate)))
        x_avant = np.linspace(0, duration, num=len(audio), endpoint=False)
        x_apres = np.linspace(0, duration, num=nb_echantillons, endpoint=False)
        reechantillonne = np.interp(
            x_apres, x_avant, audio.astype(np.float32)).astype(np.int16)
        return reechantillonne, device_rate

    @property
    def simulated(self):
        return not self.ready


# ─────────────────────────────────────────────────────────────────────────────
# Assemblage : la chaîne complète
# ─────────────────────────────────────────────────────────────────────────────
class AssistantEngine:
    """Chaîne parole → texte → réponse → voix, avec briques remplaçables."""

    # Paires utilisateur/assistant conservées dans l'historique (n_ctx=2048
    # limite la fenêtre : au-delà, les tours les plus anciens sont oubliés).
    MAX_HISTORY_TURNS = 6

    def __init__(self):
        self.stt = SpeechToText()
        self.llm = LanguageModel()
        self.tts = TextToSpeech()
        # Persiste entre redemarrages (memory_store.py, SQLite) au lieu de
        # repartir de zero a chaque relance de NOVA.
        try:
            from nova import memory_store
            self.history = memory_store.load_history(max_turns=self.MAX_HISTORY_TURNS)
        except Exception as error:
            print("[memoire] chargement historique impossible :", error)
            self.history = []  # [{"role": "user"|"assistant", "content": str}, ...]

    def _remember(self, role, content):
        self.history.append({"role": role, "content": content})
        limite = self.MAX_HISTORY_TURNS * 2
        if len(self.history) > limite:
            self.history = self.history[-limite:]
        try:
            from nova import memory_store
            memory_store.append_turn(role, content, max_turns=self.MAX_HISTORY_TURNS)
        except Exception as error:
            print("[memoire] sauvegarde tour impossible :", error)

    def reset_conversation(self):
        """Efface l'historique (ex. bouton « nouvelle conversation »)."""
        self.history = []
        try:
            from nova import memory_store
            memory_store.clear_history()
        except Exception as error:
            print("[memoire] effacement impossible :", error)

    def status(self):
        """Décrit l'état des trois briques (réel ou simulé)."""
        return {
            "stt": "réel" if not self.stt.simulated else "simulation",
            "llm": "réel" if not self.llm.simulated else "simulation",
            "tts": "réel" if not self.tts.simulated else "simulation",
        }

    def fully_simulated(self):
        return self.stt.simulated and self.llm.simulated and self.tts.simulated

    def transcribe(self, audio_data=None):
        return self.stt.transcribe(audio_data)

    def respond(self, text, on_token=None, app=None):
        """Génère une réponse. Si le LLM produit une commande d'action, elle est
        exécutée et la confirmation est renvoyée ; sinon, réponse en texte.

        app : référence à l'application NOVA (pour agir sur agenda, navigation…).

        Diffuse la réponse token par token dès que possible (vrai streaming
        llama.cpp) : une réponse en texte libre s'affiche donc au fur et à
        mesure de sa génération. Une commande d'action (le premier caractère
        non-blanc est "{") reste muette tant qu'elle n'est pas complète, pour
        ne jamais afficher de JSON brut à l'écran.

        Un chemin rapide (sans LLM) traite d'abord les commandes courtes et
        non-ambiguës (ouvrir une app, changer de mode/thème, heure, aide...) :
        réponse instantanée et fiable à 100 %, sans attendre le modèle.
        """
        from nova import assistant_actions as actions

        rapide = actions.try_fast_path(text)
        # Audit : aucune trace de quel chemin traite une commande -> impossible
        # de savoir si une commande ratee est passee par le LLM (peu fiable
        # pour le JSON) ou par le chemin rapide (fiable a 100%).
        print("[ia] chemin rapide :", rapide if rapide is not None else "aucun (-> LLM)")
        if rapide is not None:
            # Meta-action sur l'IA elle-meme (pas un appareil a piloter) :
            # traitee ici, pas dans assistant_actions.execute_action qui
            # n'a pas de reference au moteur.
            if rapide.get("action") == "effacer_historique":
                self.reset_conversation()
                confirmation = "Historique effacé."
                if on_token:
                    for word in confirmation.split(" "):
                        on_token(word + " ")
                        time.sleep(0.02)
                return confirmation
            confirmation = actions.execute_action(rapide, app=app)
            if confirmation:
                if on_token:
                    for word in confirmation.split(" "):
                        on_token(word + " ")
                        time.sleep(0.02)
                self._remember("user", text)
                self._remember("assistant", confirmation)
                return confirmation

        if self.llm.ready and self.llm.model is not None:
            system = actions.build_system_prompt()
            messages = [{"role": "system", "content": system}]
            messages.extend(self.history)
            messages.append({"role": "user", "content": text})

            raw = ""
            first_char = None
            try:
                stream = self.llm.model.create_chat_completion(
                    messages=messages,
                    max_tokens=256,
                    # Audit : un modele 3B quantifie ecrivait parfois une
                    # confirmation en texte libre ("C'est note...") sans le
                    # JSON d'action correspondant -> aucune action reellement
                    # executee, mais l'utilisateur croyait le contraire.
                    # Baisse encore la temperature (fiabilite JSON, cf.
                    # REGLE ABSOLUE du prompt systeme dans assistant_actions.py).
                    temperature=0.2,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk["choices"][0].get("delta", {})
                    piece = delta.get("content", "")
                    if not piece:
                        continue
                    raw += piece
                    if first_char is None:
                        stripped = raw.lstrip()
                        if stripped:
                            first_char = stripped[0]
                    if first_char is not None and first_char != "{" and on_token:
                        on_token(piece)
            except Exception as error:
                print("[llm] erreur de génération :", error)
                raw = ""
            raw = raw.strip()

            reply = None
            data = actions.extract_json(raw)
            if data is not None:
                confirmation = actions.execute_action(data, app=app)
                if confirmation:
                    reply = confirmation
                    # Muette pendant le streaming (JSON) : "tapee" a la fin.
                    if on_token:
                        for word in confirmation.split(" "):
                            on_token(word + " ")
                            time.sleep(0.02)
            if reply is None and raw:
                reply = raw
                if first_char == "{" and on_token:
                    # Ressemblait a une action mais JSON invalide/sans
                    # confirmation : jamais diffusee plus haut, on la montre.
                    for word in raw.split(" "):
                        on_token(word + " ")
                        time.sleep(0.02)

            if reply:
                self._remember("user", text)
                self._remember("assistant", reply)
                return reply

        # Repli : pas de vrai LLM -> simulation (pas de memoire, cas degrade)
        return self.llm.generate(text, on_token=on_token)

    def say(self, text):
        return self.tts.speak(text)


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    """Instance partagée du moteur (chargée une seule fois).

    Appelée depuis plusieurs threads (pipeline vocal, pipeline texte, alerte
    d'événement) : sans verrou, un check-then-set non atomique sur _engine
    laissait deux threads charger simultanément Whisper+LLM+Piper (~2,4 Go).
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = AssistantEngine()
    return _engine
