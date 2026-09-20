"""
Offline speech-to-text using Vosk.

Requires a Vosk model directory on disk (not bundled — must be downloaded
once). Recommended small English model (~40MB):

    wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
    unzip vosk-model-small-en-us-0.15.zip -d models/

Then set VOSK_MODEL_PATH below (or pass model_path explicitly) to point at
the unzipped folder, e.g. "models/vosk-model-small-en-us-0.15".

The default path is resolved relative to this script's own location (not
the current working directory), so it works the same whether you run it
from this folder directly, from a systemd service, or from a cron job
launched elsewhere.
"""

import json
import os

SAMPLE_RATE = 16000
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VOSK_MODEL_PATH = os.path.join(SCRIPT_DIR, "models", "vosk-model-small-en-us-0.15")
VOSK_MODEL_PATH = os.environ.get("VOSK_MODEL_PATH", DEFAULT_VOSK_MODEL_PATH)


class SpeechRecognizer:
    def __init__(self, model_path: str = VOSK_MODEL_PATH):
        self.available = False
        self.model = None
        self._error = None

        if not os.path.isdir(model_path):
            self._error = (
                f"Vosk model not found at '{model_path}'. Download it with:\n"
                f"  wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip\n"
                f"  unzip vosk-model-small-en-us-0.15.zip -d models/"
            )
            print(f"[Speech recognizer unavailable — {self._error}]")
            return

        try:
            from vosk import Model
            self.model = Model(model_path)
            self.available = True
        except Exception as e:
            self._error = e
            print(f"[Speech recognizer unavailable — {e}]")

    def listen_and_transcribe(self, duration_seconds: float = 4.0) -> str:
        """
        Records `duration_seconds` of audio from the default mic and returns
        the transcribed text (lowercase). Returns "" if nothing was heard.
        Raises RuntimeError if the recognizer isn't available.
        """
        if not self.available:
            raise RuntimeError(f"Speech recognizer not ready: {self._error}")

        try:
            import sounddevice as sd
        except Exception as e:
            raise RuntimeError(f"Audio library unavailable: {e}")
        from vosk import KaldiRecognizer

        recognizer = KaldiRecognizer(self.model, SAMPLE_RATE)
        print(f"🎙️  Recording for {duration_seconds}s...")

        try:
            audio = sd.rec(
                int(duration_seconds * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
            )
            sd.wait()
        except Exception as e:
            raise RuntimeError(f"Microphone recording failed: {e}")

        recognizer.AcceptWaveform(audio.tobytes())
        result = json.loads(recognizer.FinalResult())
        text = result.get("text", "").strip().lower()
        print(f"📝 Heard: '{text}'" if text else "📝 (nothing recognized)")
        return text