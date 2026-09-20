#!/usr/bin/env python3
"""
JARVIS-style alarm clock — Phase 1 MVP

Flow:
  1. Waits until configured wake time (or fires immediately with --test)
  2. "Wakes" the user (beep + prompt) and waits for a typed response
  3. Once acknowledged, loads today's schedule and picks the top priorities
  4. Speaks/prints a JARVIS-style morning briefing

Phase 2: wake-word detection (openWakeWord "hey jarvis") and offline speech
recognition (Vosk) are now used when available, falling back to typed input
if no mic or model is present — so this still runs on a laptop with no
audio hardware set up yet.

Remaining swap points for later phases (see README.md):
  - load_tasks(): replace tasks.json with a real Google Calendar / Todoist pull
  - speak(): replace pyttsx3 with ElevenLabs or a Raspberry Pi speaker output
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime

from wake_word import WakeWordListener
from speech_to_text import SpeechRecognizer
from piper_tts import PiperSpeaker

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
TASKS_PATH = os.path.join(os.path.dirname(__file__), "tasks.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "wake_log.txt")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_tasks():
    with open(TASKS_PATH) as f:
        return json.load(f)


def log_event(message: str):
    with open(LOG_PATH, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {message}\n")


_tts_engine = None
_piper_speaker = None


def _get_tts_engine():
    """
    Returns a persistent pyttsx3 engine instance instead of creating a new
    one each call. Re-initializing the engine every time is what caused the
    speech to cut off mid-sentence: on Linux, the espeak driver runs
    synthesis via a background callback that holds a weak reference to the
    engine's proxy object. If the engine goes out of scope and gets garbage
    collected right as the script exits, that callback fires after the
    proxy is already gone (ReferenceError) and the audio is cut off before
    it finishes playing.
    """
    global _tts_engine
    if _tts_engine is None:
        import pyttsx3
        _tts_engine = pyttsx3.init()
    return _tts_engine


def _get_piper_speaker(voice_name: str):
    global _piper_speaker
    if _piper_speaker is None:
        _piper_speaker = PiperSpeaker(voice_name=voice_name)
    return _piper_speaker


def speak(text: str, config: dict):
    """
    Speak text aloud, otherwise print it.
    Tries Piper first (much more natural voice) if tts_engine allows it,
    falling back to espeak/pyttsx3, then to plain text if neither works.
    """
    print(f"\n🤖 {text}\n")
    if not config.get("tts_enabled", True):
        return

    engine_pref = config.get("tts_engine", "auto")  # "piper", "espeak", or "auto"

    if engine_pref in ("piper", "auto"):
        try:
            piper = _get_piper_speaker(config.get("piper_voice", "en_GB-alan-medium"))
            piper.speak(
                text,
                length_scale=config.get("piper_length_scale", 1.0),
                volume=config.get("piper_volume", 1.0),
            )
            return
        except RuntimeError as e:
            print(f"[Piper unavailable, falling back to espeak — {e}]")

    try:
        engine = _get_tts_engine()
        # espeak-ng's default rate (~200 wpm) often sounds slurred/"blurry" —
        # slowing it down usually clears this up. Default volume of 1.0 can
        # also clip/distort on some audio setups; 0.9 gives headroom.
        rate = config.get("tts_rate")
        volume = config.get("tts_volume")
        if rate is not None:
            engine.setProperty("rate", rate)
        if volume is not None:
            engine.setProperty("volume", volume)
        engine.say(text)
        engine.runAndWait()
        engine.stop()  # ensure the driver fully drains before we move on
    except Exception as e:
        # No audio device / espeak in this environment, or pyttsx3 missing.
        # This is expected on headless servers — falls back to text silently.
        print(f"[TTS unavailable, printed only — {e}]")


def wait_until_wake_time(wake_time: str, check_interval: int):
    """Block until the clock reaches wake_time (HH:MM), checking periodically."""
    print(f"Waiting for wake time {wake_time}... (Ctrl+C to stop)")
    while True:
        now = datetime.now().strftime("%H:%M")
        if now == wake_time:
            return
        time.sleep(check_interval)


def wait_for_wake_response_typed(assistant_name: str, snooze_minutes: int):
    """Fallback wake-detection: typed response (used if voice isn't available)."""
    while True:
        response = input(
            f"⏰ {assistant_name}: Good morning. Type anything to confirm you're up "
            f"(or 'snooze'): "
        ).strip().lower()
        if response == "snooze":
            print(f"Snoozing for {snooze_minutes} minutes...")
            time.sleep(snooze_minutes * 60)
            continue
        log_event("User acknowledged wake-up (typed)")
        return response


def wait_for_wake_response_voice(assistant_name: str, snooze_minutes: int,
                                  wake_listener: WakeWordListener,
                                  recognizer: SpeechRecognizer):
    """
    Phase 2 wake-detection: listens for the "hey jarvis" wake word, then
    records and transcribes a short response to check for "snooze".
    Falls back to typed input if the wake word isn't heard within a
    reasonable time or the mic/model isn't available.
    """
    while True:
        try:
            wake_listener.wait_for_wakeword()
        except RuntimeError as e:
            print(f"[Falling back to typed input — {e}]")
            return wait_for_wake_response_typed(assistant_name, snooze_minutes)

        text = ""
        try:
            text = recognizer.listen_and_transcribe(duration_seconds=4.0)
        except RuntimeError as e:
            print(f"[Speech-to-text unavailable, treating wake word as confirmation — {e}]")
            log_event("User acknowledged wake-up (voice, no STT)")
            return "up"

        if "snooze" in text:
            print(f"Snoozing for {snooze_minutes} minutes...")
            time.sleep(snooze_minutes * 60)
            continue

        log_event(f"User acknowledged wake-up (voice): '{text}'")
        return text or "up"


def pick_top_priorities(events, api_key_env: str, max_items: int = 2):
    """
    Pick the top priorities for the day.
    Uses the Anthropic API for a natural-language summary if an API key is
    configured; otherwise falls back to a simple rule (sort by priority).
    """
    api_key = os.environ.get(api_key_env)

    if api_key:
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            events_text = "\n".join(
                f"- {e['time']} {e['title']} (priority: {e['priority']})" for e in events
            )
            prompt = (
                "You are JARVIS, a calm and efficient AI assistant, briefing your "
                "principal right after they wake up. Here is today's schedule:\n\n"
                f"{events_text}\n\n"
                f"In 2-3 short sentences, identify the top {max_items} priorities for "
                "today and state them in JARVIS's voice — brief, composed, a little dry wit. "
                "Do not list every event, just the top priorities."
            )
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            print(f"[LLM summary unavailable, using fallback — {e}]")

    # Fallback: no API key or call failed — simple rule-based summary
    high_priority = [e for e in events if e.get("priority") == "high"][:max_items]
    if not high_priority:
        high_priority = events[:max_items]
    items = "; ".join(f"{e['title']} at {e['time']}" for e in high_priority)
    return f"Your top priorities today: {items}."


def run(test_mode: bool):
    config = load_config()
    tasks = load_tasks()

    assistant_name = config["assistant_name"]
    user_name = config["user_name"]

    if not test_mode:
        wait_until_wake_time(config["wake_time"], config["check_interval_seconds"])
    else:
        print("[--test mode: skipping wait, triggering alarm immediately]")

    log_event("Alarm triggered")

    wake_listener = WakeWordListener()
    recognizer = SpeechRecognizer()

    if wake_listener.available:
        wait_for_wake_response_voice(
            assistant_name, config["snooze_minutes"], wake_listener, recognizer
        )
    else:
        wait_for_wake_response_typed(assistant_name, config["snooze_minutes"])

    briefing = pick_top_priorities(
        tasks["events"], config["anthropic_api_key_env"]
    )
    greeting = f"Good morning, {user_name}. {briefing}"

    speak(greeting, config)
    log_event(f"Briefing delivered: {briefing}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS-style alarm clock (Phase 1 MVP)")
    parser.add_argument(
        "--test", action="store_true",
        help="Skip waiting for the configured wake time and trigger immediately"
    )
    args = parser.parse_args()

    try:
        run(test_mode=args.test)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
