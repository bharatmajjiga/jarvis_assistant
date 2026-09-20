"""
Wake-word detection using openWakeWord's built-in 'hey jarvis' model.

No model download needed — hey_jarvis_v0.1.onnx ships inside the
openwakeword pip package itself.

Usage:
    listener = WakeWordListener()
    if listener.available:
        listener.wait_for_wakeword()   # blocks until "hey jarvis" is heard
"""

import os
import glob
import numpy as np

CHUNK_SAMPLES = 1280  # 80ms at 16kHz, the frame size openWakeWord expects
SAMPLE_RATE = 16000
DETECTION_THRESHOLD = 0.5


def _find_bundled_model(name: str = "hey_jarvis"):
    """Locate the bundled .onnx model file inside the installed package."""
    import openwakeword
    pkg_dir = os.path.dirname(openwakeword.__file__)
    matches = glob.glob(os.path.join(pkg_dir, "resources", "models", f"{name}*.onnx"))
    return matches[0] if matches else None


class WakeWordListener:
    def __init__(self, wakeword: str = "hey_jarvis", threshold: float = DETECTION_THRESHOLD):
        self.threshold = threshold
        self.available = False
        self.model = None
        self.model_key = None
        self._stream_error = None

        try:
            from openwakeword.model import Model
            model_path = _find_bundled_model(wakeword)
            if not model_path:
                raise FileNotFoundError(f"No bundled model found for '{wakeword}'")
            self.model = Model(wakeword_model_paths=[model_path])
            self.model_key = list(self.model.models.keys())[0]
            self.available = True
        except Exception as e:
            self._stream_error = e
            print(f"[Wake-word model unavailable — {e}]")

    def wait_for_wakeword(self, timeout_seconds: float = None) -> bool:
        """
        Blocks, listening on the default microphone, until the wake word is
        detected. Returns True if detected, False on timeout.
        Raises RuntimeError if no mic is available (caller should fall back
        to typed input in that case).
        """
        if not self.available:
            raise RuntimeError(f"Wake-word model not loaded: {self._stream_error}")

        try:
            import sounddevice as sd
        except Exception as e:
            raise RuntimeError(f"Audio library unavailable: {e}")
        import time

        print(f"👂 Listening for 'Hey JARVIS'...")
        start = time.time()
        detected = {"flag": False}

        def callback(indata, frames, time_info, status):
            if detected["flag"]:
                return
            audio = indata[:, 0].astype(np.int16)
            prediction = self.model.predict(audio)
            score = prediction.get(self.model_key, 0)
            if score > self.threshold:
                detected["flag"] = True

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=CHUNK_SAMPLES,
                channels=1,
                dtype="int16",
                callback=callback,
            ):
                while not detected["flag"]:
                    if timeout_seconds and (time.time() - start) > timeout_seconds:
                        return False
                    time.sleep(0.05)
        except Exception as e:
            raise RuntimeError(f"Microphone stream failed: {e}")

        print("✅ Wake word detected!")
        return True
