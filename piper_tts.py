"""
Offline neural text-to-speech using Piper — noticeably clearer and more
natural than espeak, still fully offline (no API key, no internet needed
once the voice model is downloaded).

Requires a Piper voice model (.onnx + .onnx.json), downloaded once:

    python3 -m piper.download_voices en_GB-alan-medium --download-dir models/piper

Good JARVIS-ish voice options:
  - en_GB-alan-medium   — deeper, British accent, good default for this project
  - en_US-ryan-high     — clear American voice, higher quality/larger model
  - en_US-lessac-medium — solid general-purpose American voice

Run `python3 -m piper.download_voices` with no arguments to list all
available voices.
"""

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PIPER_MODEL_DIR = os.path.join(SCRIPT_DIR, "models", "piper")
DEFAULT_VOICE_NAME = os.environ.get("PIPER_VOICE", "en_GB-alan-medium")


class PiperSpeaker:
    def __init__(self, voice_name: str = DEFAULT_VOICE_NAME, model_dir: str = DEFAULT_PIPER_MODEL_DIR):
        self.available = False
        self.voice = None
        self._error = None

        model_path = os.path.join(model_dir, f"{voice_name}.onnx")
        config_path = os.path.join(model_dir, f"{voice_name}.onnx.json")

        if not (os.path.isfile(model_path) and os.path.isfile(config_path)):
            self._error = (
                f"Piper voice not found at '{model_path}'. Download it with:\n"
                f"  python3 -m piper.download_voices {voice_name} --download-dir {model_dir}"
            )
            print(f"[Piper unavailable — {self._error}]")
            return

        try:
            from piper import PiperVoice
            self.voice = PiperVoice.load(model_path, config_path)
            self.available = True
        except Exception as e:
            self._error = e
            print(f"[Piper unavailable — {e}]")

    def speak(self, text: str, length_scale: float = 1.0, volume: float = 1.0):
        """
        Synthesize and play text aloud through the default output device.
        Raises RuntimeError if the voice model or audio playback isn't available.
        length_scale: >1.0 slows speech down, <1.0 speeds it up (inverse of
        pyttsx3's "rate" — this is a multiplier on duration, not words/minute).
        """
        if not self.available:
            raise RuntimeError(f"Piper not ready: {self._error}")

        try:
            import numpy as np
            import sounddevice as sd
        except Exception as e:
            raise RuntimeError(f"Audio playback library unavailable: {e}")

        from piper.config import SynthesisConfig

        syn_config = SynthesisConfig(length_scale=length_scale, volume=volume)
        chunks = list(self.voice.synthesize(text, syn_config=syn_config))
        if not chunks:
            return

        sample_rate = chunks[0].sample_rate
        audio = np.concatenate([c.audio_float_array for c in chunks])

        try:
            sd.play(audio, sample_rate)
            sd.wait()
        except Exception as e:
            # No output device (e.g. no /dev/snd in a container, or no
            # speakers attached) — synthesis succeeded but playback failed.
            # Let the caller fall back to espeak/print rather than crash.
            raise RuntimeError(f"Audio playback failed: {e}")