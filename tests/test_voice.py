"""Tests for the optional voice layer's graceful degradation.

These assert behaviour when the `voice` extra is absent (the common case on a
plain install and in CI), so they must pass with or without the backends.
"""

import donald.voice as voice


def test_speaker_disabled_without_backend():
    sp = voice.Speaker(enabled=True)
    # Enabled only if the TTS backend is actually importable.
    assert sp.enabled == voice.tts_available()


def test_speak_never_raises():
    sp = voice.Speaker(enabled=True)
    sp.speak("this must not crash, audio or not")
    sp.speak("")  # empty is a no-op


def test_toggle_reports_missing_extra():
    sp = voice.Speaker(enabled=False)
    enabled, note = sp.toggle()
    if voice.tts_available():
        assert enabled is True and "on" in note.lower()
    else:
        assert enabled is False and "voice" in note.lower()


def test_listen_once_without_backend():
    transcript, note = voice.listen_once()
    if not voice.stt_available():
        assert transcript is None
        assert "voice" in note.lower()
