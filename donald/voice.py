"""Donald's optional voice layer — spoken replies (TTS) and spoken input (STT).

Voice is strictly optional. The dependencies live in the `voice` extra
(``pip install 'donald[voice]'``) and need a working speaker/microphone, so on
a headless box or without the extra installed everything here degrades to a
clear message instead of crashing. The rest of Donald works untouched.

- Output: `Speaker.speak()` reads replies aloud via pyttsx3 (offline).
- Input:  `listen_once()` captures one spoken phrase via SpeechRecognition.
"""

from __future__ import annotations

import importlib.util

_VOICE_HINT = "needs the `voice` extra:  pip install 'donald[voice]'"


def _installed(module: str) -> bool:
    """True if an import would succeed, without actually importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def tts_available() -> bool:
    return _installed("pyttsx3")


def stt_available() -> bool:
    return _installed("speech_recognition")


class Speaker:
    """Reads text aloud, when enabled and the TTS backend is present."""

    def __init__(self, enabled: bool = False) -> None:
        # Only truly enable if the backend exists; otherwise stay silent.
        self.enabled = bool(enabled) and tts_available()
        self._engine = None  # lazily initialised on first use

    def _engine_or_none(self):
        if self._engine is None:
            try:
                import pyttsx3

                self._engine = pyttsx3.init()
            except Exception:
                return None
        return self._engine

    def speak(self, text: str) -> None:
        """Say `text`. Never raises — speech must not break the REPL."""
        if not self.enabled or not text.strip():
            return
        engine = self._engine_or_none()
        if engine is None:
            return
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass

    def toggle(self) -> tuple[bool, str]:
        """Flip spoken output. Returns (now_enabled, message_for_operator)."""
        if self.enabled:
            self.enabled = False
            return False, "Spoken replies off."
        if not tts_available():
            return False, f"Voice output {_VOICE_HINT}"
        self.enabled = True
        return True, "Spoken replies on."


def listen_once(timeout: int = 8, phrase_limit: int = 20) -> tuple[str | None, str]:
    """Capture one spoken phrase. Returns (transcript_or_None, note).

    `note` explains why nothing was captured (missing extra, no mic, silence),
    so the caller can show it. Never raises.
    """
    if not stt_available():
        return None, f"Voice input {_VOICE_HINT}"
    try:
        import speech_recognition as sr
    except Exception as exc:  # backend present but broken
        return None, f"Voice input unavailable: {exc}"

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
    except OSError as exc:
        return None, f"Couldn't access the microphone: {exc}"
    except Exception as exc:  # e.g. listen() timeout waiting for speech
        return None, f"Didn't hear anything: {exc}"

    try:
        return recognizer.recognize_google(audio), ""
    except sr.UnknownValueError:
        return None, "Didn't catch that — try again."
    except Exception as exc:
        return None, f"Speech recognition failed: {exc}"
