"""Tests for the always-on wake listener's decision logic.

The audio loop needs a microphone + Vosk, but the part that matters — *when* to
launch — is pure and tested here with an injected clock and on_wake callback.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from donald.listener import WakeListener, wake_word_in  # noqa: E402


def test_wake_word_matches_variants():
    assert wake_word_in("donald")
    assert wake_word_in("hey donald what time is it")
    assert wake_word_in("the donald open safari")
    assert wake_word_in("donal")  # common Vosk near-miss


def test_wake_word_ignores_unrelated_and_substrings():
    assert not wake_word_in("")
    assert not wake_word_in("what's the weather")
    assert not wake_word_in("mcdonalds menu")  # substring must not trigger


def test_handle_text_fires_once_and_respects_cooldown():
    fired = []
    wl = WakeListener(on_wake=lambda: fired.append(True), cooldown=6.0)

    assert wl.handle_text("donald", now=100.0) is True
    assert len(fired) == 1
    # Same wake word again within the cooldown window: no relaunch.
    assert wl.handle_text("donald open mail", now=103.0) is False
    assert len(fired) == 1
    # After the cooldown, it can fire again.
    assert wl.handle_text("donald", now=107.0) is True
    assert len(fired) == 2


def test_handle_text_ignores_non_wake_text():
    fired = []
    wl = WakeListener(on_wake=lambda: fired.append(True))
    assert wl.handle_text("just talking to myself", now=1.0) is False
    assert fired == []
