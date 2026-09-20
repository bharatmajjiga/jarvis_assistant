# JARVIS Alarm Clock — container image
#
# Multi-arch base: python:3.12.3-slim-bookworm builds on both amd64 (Fedora
# laptop) and arm64 (Raspberry Pi 4, aarch64) from the same Dockerfile.
#
# Audio hardware (mic/speaker) is not available inside a container by
# default. To actually use the mic/speaker once you have them, run with:
#   docker run --device /dev/snd ...
# Without that flag, the app still runs end to end via the same graceful
# fallback tested throughout development (voice -> typed input, Piper ->
# espeak -> print).

FROM python:3.12.3-slim-bookworm

# System dependencies:
#   espeak-ng      - TTS fallback voice (pyttsx3)
#   libespeak-ng1  - shared library pyttsx3's espeak driver links against
#   portaudio19-dev / libportaudio2 - mic and speaker access (sounddevice, Piper)
#   alsa-utils     - provides `aplay`, which pyttsx3's espeak driver shells
#                    out to for playback; without it espeak "succeeds" but
#                    produces no sound (silently, via a swallowed subprocess
#                    error) instead of raising a catchable exception
#   pipewire-alsa  - client-side ALSA plugin that lets this container's
#                    ALSA calls route through the HOST's already-running
#                    PipeWire session (mounted in at runtime, see README)
#                    instead of talking to raw hardware directly. This
#                    matters because modern laptop mic arrays (Intel SOF
#                    DMIC, seen here) need PipeWire/WirePlumber's DSP and
#                    gain correction to produce usable signal — raw ALSA
#                    access to the same hardware can open successfully but
#                    capture silence or garbage.
#   wget, unzip    - fetching the Vosk model at build or run time
#   gcc            - some packages (e.g. sounddevice's cffi backend) build
#                    a small C extension on first install
RUN apt-get update && apt-get install -y --no-install-recommends \
    espeak-ng \
    libespeak-ng1 \
    portaudio19-dev \
    libportaudio2 \
    alsa-utils \
    pipewire-alsa \
    wget \
    unzip \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/user/0

WORKDIR /app

# Install Python dependencies first (separate layer — only rebuilds when
# requirements.txt changes, not on every source edit)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download models at build time so the image is self-contained and doesn't
# need internet access at container start (useful once this runs standalone
# in the figure, potentially without reliable wifi at boot)
RUN mkdir -p models/piper && \
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O /tmp/vosk.zip && \
    unzip -q /tmp/vosk.zip -d models/ && \
    rm /tmp/vosk.zip && \
    python3 -m piper.download_voices en_GB-alan-medium --download-dir models/piper

# Now copy the application source (changes here don't invalidate the
# dependency/model layers above)
COPY *.py .
COPY config.json tasks.json .

# Anthropic API key is passed at run time, not baked into the image:
#   docker run -e ANTHROPIC_API_KEY=sk-ant-... ...
# wake_log.txt is written inside the container by default; mount a volume
# if you want it to persist across container restarts:
#   docker run -v ./wake_log.txt:/app/wake_log.txt ...

ENTRYPOINT ["python3", "jarvis_alarm.py"]
CMD ["--test"]