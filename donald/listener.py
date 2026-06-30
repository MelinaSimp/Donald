"""Always-on wake listener — say "Donald" from anywhere, the app opens.

This is the piece that makes Donald feel alive: a small background process that
listens to the microphone for the wake word and, when it hears **"Donald"**,
makes sure the app server is running and opens the UI *armed* — so you can talk
immediately without clicking anything or repeating yourself.

    python -m donald.listener        # runs forever, listening

Speech recognition for the wake word runs **offline** via Vosk (no audio leaves
the machine, no per-utterance network call). Vosk + a small model are an
optional install — see :func:`_load_recognizer` for the one-time setup.

The audio loop is deliberately thin: it streams mic frames into Vosk and feeds
recognized text to :meth:`WakeListener.handle_text`, which holds all the real
logic (wake-word matching, cooldown, launching). That split keeps the
decision-making testable without a microphone.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from typing import Callable, Optional

from .app import DEFAULT_PORT, HOST

# Vosk often mishears a single name; accept the near-misses the small model
# tends to produce for "Donald" so the wake word actually triggers in practice.
WAKE_VARIANTS = ("donald", "donalds", "donal", "donuld", "donnald", "the donald")

# Don't relaunch on every frame while you're still saying the command.
DEFAULT_COOLDOWN = 6.0


def wake_word_in(text: str, variants=WAKE_VARIANTS) -> bool:
    """True if any wake-word variant appears as a whole word in ``text``."""
    if not text:
        return False
    padded = f" {text.lower().strip()} "
    return any(f" {v} " in padded for v in variants)


@dataclass
class WakeListener:
    """Holds the wake decision logic; the audio loop just feeds it text."""

    url: str = f"http://{HOST}:{DEFAULT_PORT}/"
    cooldown: float = DEFAULT_COOLDOWN
    # Injected so tests can drive these without a real server/browser/clock.
    on_wake: Optional[Callable[[], None]] = None
    _last_fire: float = field(default=-1e9, repr=False)

    # -- the decision (pure, testable) ------------------------------------
    def handle_text(self, text: str, now: float) -> bool:
        """Given recognized text and the current time, fire once if it's the wake word.

        Returns ``True`` if this call triggered a launch. Honors the cooldown so
        a long command ("Donald, ... donald ...") only launches once.
        """
        if not wake_word_in(text):
            return False
        if now - self._last_fire < self.cooldown:
            return False
        self._last_fire = now
        (self.on_wake or self._wake)()
        return True

    # -- the effect (launch the app) --------------------------------------
    def _wake(self) -> None:
        self._ensure_server()
        self._open_ui()

    def _server_up(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "api/health", timeout=1.5) as r:
                return json.loads(r.read()).get("ok") is True
        except Exception:
            return False

    def _ensure_server(self) -> None:
        if self._server_up():
            return
        # Launch the app server detached, without it opening its own browser tab.
        subprocess.Popen(
            [sys.executable, "-m", "donald.app", "--no-browser"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(20):  # wait up to ~5s for it to come up
            time.sleep(0.25)
            if self._server_up():
                return

    def _open_ui(self) -> None:
        # ?armed=1 tells the UI to start capturing a command immediately.
        webbrowser.open(self.url + "?armed=1")

    # -- the audio loop (needs a mic + Vosk) ------------------------------
    def run(self) -> None:
        """Listen to the microphone forever, launching on the wake word."""
        rec, stream_ctx, samplerate = _load_recognizer()
        print('Donald is listening. Say "Donald" from anywhere. (Ctrl-C to stop.)')
        try:
            with stream_ctx as stream:
                while True:
                    data, _ = stream.read(4000)
                    if rec.AcceptWaveform(bytes(data)):
                        text = json.loads(rec.Result()).get("text", "")
                    else:
                        text = json.loads(rec.PartialResult()).get("partial", "")
                    if self.handle_text(text, time.monotonic()):
                        print('Heard "Donald" — opening the app.')
        except KeyboardInterrupt:
            print("\nStopped listening.")


def _load_recognizer():
    """Build the Vosk recognizer + mic stream, with a friendly setup error.

    One-time setup on the user's machine::

        pip install vosk sounddevice           # macOS also: brew install portaudio
        # download a small model, unzip to ./model:
        #   https://alphacephei.com/vosk/models  (vosk-model-small-en-us-0.15)
    """
    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit(
            "The wake listener needs Vosk + sounddevice:\n"
            "  pip install vosk sounddevice   (macOS: brew install portaudio first)\n"
            "then download a small model from https://alphacephei.com/vosk/models\n"
            "and unzip it to a folder named 'model' in the project root.\n"
            f"(import failed: {exc})"
        )
    import os

    model_path = os.environ.get("VOSK_MODEL", "model")
    if not os.path.isdir(model_path):  # pragma: no cover - environment-dependent
        raise SystemExit(
            f"No Vosk model at '{model_path}'. Download vosk-model-small-en-us-0.15 "
            "from https://alphacephei.com/vosk/models, unzip it, and either name the "
            "folder 'model' or set VOSK_MODEL=/path/to/model."
        )
    samplerate = 16000
    model = Model(model_path)
    rec = KaldiRecognizer(model, samplerate)
    stream = sd.RawInputStream(
        samplerate=samplerate, blocksize=8000, dtype="int16", channels=1
    )
    return rec, stream, samplerate


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Donald — always-on wake listener")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--cooldown", type=float, default=DEFAULT_COOLDOWN)
    args = parser.parse_args()
    WakeListener(url=f"http://{HOST}:{args.port}/", cooldown=args.cooldown).run()


if __name__ == "__main__":
    main()
