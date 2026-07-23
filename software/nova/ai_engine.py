#!/usr/bin/env python3
"""Moteur d'intelligence artificielle local : STT -> LLM -> TTS.

  - STT : Whisper (binaire `whisper`)
  - LLM : llama.cpp (binaire `llama-cli` ou `main`) + modèle GGUF
  - TTS : Piper (binaire `piper`) + voix ONNX

Chaque brique est optionnelle : si un binaire ou un modèle manque, le moteur
le signale au lieu de planter.
"""

import os
import subprocess
import tempfile

from nova.paths import MODELS_DIR
from nova.utils.config_loader import get_config
from nova.utils.platform_utils import has_command

SYSTEM_PROMPT = (
    "Tu es NOVA, un assistant personnel portable embarque. "
    "Reponds en francais, de facon concise et utile, en 3 phrases maximum."
)


class NovaAI:
    """Pipeline IA complet, 100 % local."""

    def __init__(self):
        ai_conf = get_config().get("ai", {})
        self.whisper_model = ai_conf.get("whisper_model", "tiny")
        self.llm_model = MODELS_DIR / ai_conf.get("llm_model", "model.gguf")
        self.tts_model = MODELS_DIR / ai_conf.get("tts_voice", "voice.onnx")
        self.context = []
        self.max_context = 5

    # --- diagnostics ----------------------------------------------------
    def status(self):
        return {
            "stt": has_command("whisper"),
            "llm": self.llm_model.exists() and self._llama_binary() is not None,
            "tts": has_command("piper") and self.tts_model.exists(),
        }

    def is_ready(self):
        return all(self.status().values())

    def missing_parts(self):
        return [name for name, ok in self.status().items() if not ok]

    def _llama_binary(self):
        for name in ("llama-cli", "main"):
            if has_command(name):
                return name
        local = MODELS_DIR / "llama.cpp" / "llama-cli"
        if local.exists():
            return str(local)
        return None

    # --- étapes du pipeline ---------------------------------------------
    def listen(self, audio_path):
        """Audio -> texte (Whisper)."""
        if not has_command("whisper"):
            return None
        outdir = tempfile.mkdtemp(prefix="nova_stt_")
        try:
            subprocess.run(
                ["whisper", str(audio_path), "--model", self.whisper_model,
                 "--language", "fr", "--output_format", "txt",
                 "--output_dir", outdir],
                capture_output=True, text=True, timeout=120, check=False,
            )
            for name in os.listdir(outdir):
                if name.endswith(".txt"):
                    with open(os.path.join(outdir, name), "r", encoding="utf-8") as f:
                        return f.read().strip()
        except (subprocess.SubprocessError, OSError) as error:
            print("[ai] erreur STT : {}".format(error))
        return None

    def think(self, user_input):
        """Texte -> réponse (LLM local)."""
        binary = self._llama_binary()
        if binary is None or not self.llm_model.exists():
            return "Le modele de langage n'est pas installe."

        prompt = self.build_prompt(user_input)
        try:
            result = subprocess.run(
                [binary, "-m", str(self.llm_model), "-p", prompt,
                 "-n", "150", "--temp", "0.7", "-no-cnv"],
                capture_output=True, text=True, timeout=180, check=False,
            )
            response = result.stdout.replace(prompt, "").strip()
            if not response:
                return "Je n'ai pas de reponse a donner."
            self.context.append({"user": user_input, "assistant": response})
            self.context = self.context[-self.max_context:]
            return response
        except (subprocess.SubprocessError, OSError) as error:
            print("[ai] erreur LLM : {}".format(error))
            return "Desole, une erreur est survenue."

    def speak(self, text):
        """Texte -> parole (Piper + aplay)."""
        if not has_command("piper") or not self.tts_model.exists():
            print("[ai] TTS indisponible : {}".format(text))
            return False
        output = os.path.join(tempfile.gettempdir(), "nova_tts.wav")
        try:
            subprocess.run(
                ["piper", "--model", str(self.tts_model), "--output_file", output],
                input=text, text=True, timeout=60, check=False,
            )
            if has_command("aplay"):
                subprocess.run(["aplay", "-q", output], timeout=60, check=False)
            return True
        except (subprocess.SubprocessError, OSError) as error:
            print("[ai] erreur TTS : {}".format(error))
            return False

    # --- helpers ---------------------------------------------------------
    def build_prompt(self, user_input):
        history = ""
        for turn in self.context:
            history += "Utilisateur : {}\nNOVA : {}\n".format(turn["user"], turn["assistant"])
        return "{}\n{}Utilisateur : {}\nNOVA : ".format(SYSTEM_PROMPT, history, user_input)

    def reset_context(self):
        self.context = []

    def route(self, text):
        """Détermine si la phrase relève d'une app plutôt que du LLM."""
        lowered = text.lower()
        calendar_kw = ("rappelle", "rendez-vous", "rendez vous", "evenement",
                       "événement", "rappel", "agenda", "calendrier")
        settings_kw = ("volume", "luminosite", "luminosité", "theme", "thème", "reglage", "réglage")
        if any(word in lowered for word in calendar_kw):
            return "calendar"
        if any(word in lowered for word in settings_kw):
            return "settings"
        return "chat"

    def process_audio(self, audio_path):
        """Pipeline complet : écoute -> comprend -> répond -> parle."""
        text = self.listen(audio_path)
        if not text:
            self.speak("Je n'ai pas compris, peux-tu repeter ?")
            return {"action": "error", "text": "", "response": "Non compris"}

        action = self.route(text)
        if action != "chat":
            return {"action": action, "text": text, "response": ""}

        response = self.think(text)
        self.speak(response)
        return {"action": "chat", "text": text, "response": response}


_instance = None


def get_ai():
    global _instance
    if _instance is None:
        _instance = NovaAI()
    return _instance
