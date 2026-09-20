# JARVIS Alarm Clock — Phase 2 (voice wake-word + offline STT)

A JARVIS-style alarm: wakes you, listens for you to say "Hey JARVIS" (falling
back to typed input if no mic is set up), then briefs you on today's top
priorities.

## Setup

```bash
pip install -r requirements.txt
```

**TTS (espeak)** — needed for `pyttsx3` to actually speak, not just print:
```bash
# Fedora
sudo dnf install espeak-ng
# Debian/Ubuntu (e.g. Raspberry Pi OS)
sudo apt install espeak
```
(macOS/Windows use built-in system voices — no extra install needed.)

**Mic access (PortAudio)** — needed for `sounddevice`:
```bash
# Fedora
sudo dnf install portaudio-devel
# Debian/Ubuntu (e.g. Raspberry Pi OS)
sudo apt install portaudio19-dev
```

The wake-word model ("hey jarvis") ships inside the `openwakeword` pip
package — nothing to download, same on every distro.

The speech-to-text model (Vosk) needs a one-time download:
```bash
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip -d models/
```
If this model isn't present, the script still works — it treats the wake
word alone as confirmation and skips the "did they say snooze" check.

**Voice output** now tries three engines in order, falling back gracefully:
1. **Piper** (neural, offline, much more natural — recommended) — needs a
   one-time voice download:
   ```bash
   python3 -m piper.download_voices en_GB-alan-medium --download-dir models/piper
   ```
   Other good options: `en_US-ryan-high` (clearer, bigger model),
   `en_US-lessac-medium`. List all with `python3 -m piper.download_voices`.
2. **espeak/pyttsx3** (robotic but always available) — used if Piper's
   voice model isn't downloaded yet, or `tts_engine` is set to `"espeak"`
   in `config.json`.
3. **Plain text** — used if neither audio engine works (e.g. no speakers).

Tune `piper_length_scale` (higher = slower/clearer) and `piper_volume` in
`config.json` if needed; same idea as `tts_rate`/`tts_volume` for the
espeak fallback.

**Note:** every layer here degrades gracefully. No mic → falls back to typed
input. No Vosk model → wake word alone counts as confirmation. No Piper
voice → falls back to espeak. No espeak → briefing prints instead of
speaking. You can test on a laptop with zero audio setup and it still runs
end to end (as it did during development).

For LLM-generated briefings (recommended — much more natural than the fallback),
set your Anthropic API key:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```
Without a key, it falls back to a simple rule-based summary (picks the
`high` priority events).

## Usage

```bash
# Test immediately, without waiting for the configured wake time
python3 jarvis_alarm.py --test

# Normal mode — waits until config.json's wake_time
python3 jarvis_alarm.py
```

Edit `config.json` to set your wake time, name, and assistant name.

`tasks.json` holds today's schedule (a stand-in for a real calendar
integration — see below) and is **gitignored**, since it'll contain your
real schedule/project details once you start using it. Create your own
from the template:
```bash
cp tasks.example.json tasks.json
```
Then edit `tasks.json` freely — it never gets committed.

## Files

- `jarvis_alarm.py` — main script
- `wake_word.py` — "Hey JARVIS" detection (openWakeWord, bundled model)
- `speech_to_text.py` — offline transcription of your spoken response (Vosk)
- `piper_tts.py` — natural-sounding offline voice output (Piper)
- `config.json` — wake time, names, settings
- `tasks.example.json` — template schedule (committed); copy to `tasks.json` for your own real schedule (gitignored)
- `wake_log.txt` — auto-generated log of wake times and briefings (gitignored — will contain real briefing content)

## Extension points (for Phase 2 / Phase 3)

Each of these is an isolated function — swap the implementation, keep the
rest of the pipeline unchanged:

| What to add | Where | Notes |
|---|---|---|
| Real calendar | `load_tasks()` | Pull from Google Calendar API (or Todoist/Notion) instead of `tasks.json` |
| Better voice | ✅ done | Piper wired in with espeak/print fallback |
| Raspberry Pi deployment | whole script | Runs as-is on a Pi; add a systemd service to launch on boot |
| Arc reactor LED / hardware feedback | new module | Add a WS2812 LED that pulses while "listening" and lights solid while "speaking" — trigger it around the `wait_for_wakeword()` and `speak()` calls |
| Wake streak tracking | `log_event()` | Already logging timestamps to `wake_log.txt` — parse this to compute streaks, average wake time, etc. |
| Voice commands beyond snooze | `wait_for_wake_response_voice()` | The transcribed text is already available — check for other keywords ("skip", "what's next") the same way "snooze" is checked |

## Roadmap

- **Phase 1**: software-only MVP, typed wake confirmation, manual/API task list ✅
- **Phase 2 (this)**: voice wake-word detection ("Hey JARVIS") + offline speech recognition, still laptop-testable with graceful fallback ✅
- **Phase 3**: move to the Raspberry Pi with a real mic/speaker, then integrate into a physical Iron Man figure/base — arc reactor LED, hidden speaker, optional servo-driven visor