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
import time
from pathlib import Path

from nova.paths import MODELS_DIR
from nova.utils.platform_utils import is_raspberry_pi


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

    def __init__(self, model_name="small"):
        self.model_name = model_name
        self.model = None
        self.ready = False
        self._try_load()

    def _try_load(self):
        """Charge le modèle Whisper si faster-whisper est disponible."""
        try:
            from faster_whisper import WhisperModel
            from nova.utils.platform_utils import is_raspberry_pi
            # modèle plus léger sur Pi pour la vitesse
            name = "base" if is_raspberry_pi() else self.model_name
            self.model = WhisperModel(name, device="cpu", compute_type="int8")
            self.ready = True
            print("[stt] Whisper chargé :", name)
        except Exception as error:
            print("[stt] Whisper indisponible ({}), mode simulation".format(error))
            self.model = None
            self.ready = False

    def record(self, seconds=None):
        """Enregistre depuis le micro et renvoie les échantillons audio."""
        seconds = seconds or self.RECORD_SECONDS
        try:
            import sounddevice as sd
            audio = sd.rec(int(seconds * self.SAMPLE_RATE),
                          samplerate=self.SAMPLE_RATE, channels=1, dtype="float32")
            sd.wait()
            return audio.flatten()
        except Exception as error:
            print("[stt] enregistrement micro impossible :", error)
            return None

    def transcribe(self, audio_data=None):
        """Transcrit l'audio en texte. Si audio_data est None, enregistre d'abord.

        Renvoie le texte reconnu (français).
        """
        if self.ready and self.model is not None:
            if audio_data is None:
                audio_data = self.record()
            if audio_data is None:
                return ""
            try:
                segments, _info = self.model.transcribe(audio_data, language="fr")
                text = "".join(seg.text for seg in segments).strip()
                return text
            except Exception as error:
                print("[stt] transcription impossible :", error)
                return ""
        # Repli simulation
        time.sleep(0.3)
        return random.choice(self._SIMULATED)

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
            n_threads = 4 if is_raspberry_pi() else 8
            self.model = Llama(
                model_path=str(path),
                n_ctx=2048,
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
                    sd.play(audio, samplerate=self.voice_model.config.sample_rate)
                    sd.wait()
                return True
            except Exception as error:
                print("[tts] synthèse vocale impossible :", error)
                return False
        # Simulation (silencieux, le texte reste affiché à l'écran)
        print("[tts] (simulation) prononce :", text[:60])
        return False

    @property
    def simulated(self):
        return not self.ready


# ─────────────────────────────────────────────────────────────────────────────
# Assemblage : la chaîne complète
# ─────────────────────────────────────────────────────────────────────────────
class AssistantEngine:
    """Chaîne parole → texte → réponse → voix, avec briques remplaçables."""

    def __init__(self):
        self.stt = SpeechToText()
        self.llm = LanguageModel()
        self.tts = TextToSpeech()

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
        """
        # Si le vrai LLM est là, on lui donne la liste des actions possibles et
        # on regarde s'il produit une commande JSON.
        if self.llm.ready and self.llm.model is not None:
            from nova import assistant_actions as actions

            system = actions.build_system_prompt()
            # Génération SANS streaming d'abord : on doit voir la réponse
            # complète pour savoir si c'est une action (JSON) ou du texte.
            try:
                result = self.llm.model.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": text},
                    ],
                    max_tokens=256,
                    temperature=0.4,  # plus bas = plus fiable pour le JSON
                )
                raw = result["choices"][0]["message"]["content"].strip()
            except Exception as error:
                print("[llm] erreur de génération :", error)
                raw = ""

            # Le LLM a-t-il produit une commande d'action ?
            data = actions.extract_json(raw)
            if data is not None:
                confirmation = actions.execute_action(data, app=app)
                if confirmation:
                    # « taper » la confirmation mot à mot pour l'affichage
                    if on_token:
                        for word in confirmation.split(" "):
                            on_token(word + " ")
                            time.sleep(0.03)
                    return confirmation

            # Sinon : réponse en texte libre (discussion)
            if raw:
                if on_token:
                    for word in raw.split(" "):
                        on_token(word + " ")
                        time.sleep(0.02)
                return raw

        # Repli : pas de vrai LLM -> simulation
        return self.llm.generate(text, on_token=on_token)

    def say(self, text):
        return self.tts.speak(text)


_engine = None


def get_engine():
    """Instance partagée du moteur (chargée une seule fois)."""
    global _engine
    if _engine is None:
        _engine = AssistantEngine()
    return _engine
