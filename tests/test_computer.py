"""Tests for computer-use — the see/click/type capability.

The pixel-touching paths need a display; everything else (tool spec, key
mapping, dispatch, dry-run, and the brain's beta wiring) is pure and tested
offline here.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from donald.brain import DonaldBrain  # noqa: E402
from donald.hermes import Hermes  # noqa: E402
from donald.hermes.computer import (  # noqa: E402
    COMPUTER_BETA_FLAG,
    SUPPORTED_ACTIONS,
    ComputerController,
    computer_tool_spec,
    normalize_key,
)


def test_tool_spec_shape():
    spec = computer_tool_spec(1280, 800)
    assert spec["type"] == "computer_20250124"
    assert spec["name"] == "computer"
    assert spec["display_width_px"] == 1280 and spec["display_height_px"] == 800


def test_normalize_key_maps_aliases():
    assert normalize_key("cmd+s") == ["command", "s"]
    assert normalize_key("Return") == ["enter"]
    assert normalize_key("ctrl+shift+t") == ["ctrl", "shift", "t"]
    assert normalize_key("Escape") == ["esc"]


def test_dry_run_never_touches_pixels():
    c = ComputerController(dry_run=True)
    shot = c.execute("screenshot")
    assert shot.ok and shot.image_b64 is None and "[dry-run]" in shot.output
    click = c.execute("left_click", coordinate=[10, 20])
    assert click.ok and "[dry-run]" in click.output
    assert c.execute("wait").ok


def test_unsupported_action_is_reported_not_raised():
    c = ComputerController(dry_run=True)
    r = c.execute("teleport")
    assert not r.ok and "Unsupported" in r.output


def test_supported_actions_cover_the_basics():
    assert {"screenshot", "left_click", "type", "key", "scroll"} <= SUPPORTED_ACTIONS


# -- brain integration -------------------------------------------------------

def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool_use(tid, name, inp):
    return SimpleNamespace(type="tool_use", id=tid, name=name, input=inp)


class BetaFakeClient:
    """Fake client exposing BOTH messages.create and beta.messages.create."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.beta_calls = []
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._beta_create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)

    def _beta_create(self, **kwargs):
        self.beta_calls.append(kwargs)
        return self._responses.pop(0)


def test_computer_use_routes_through_beta_and_screenshots():
    responses = [
        SimpleNamespace(
            content=[_tool_use("c1", "computer", {"action": "screenshot"})],
            stop_reason="tool_use",
        ),
        SimpleNamespace(content=[_text("Looking at your screen now.")], stop_reason="end_turn"),
    ]
    client = BetaFakeClient(responses)
    brain = DonaldBrain(
        client=client,
        hermes=Hermes(dry_run=True, enable_computer_use=True),
        personality_text="P",
    )
    result = brain.take_turn("what's on my screen")

    assert result.reply == "Looking at your screen now."
    # Went through the beta endpoint, not the plain one.
    assert client.beta_calls and not client.calls
    assert COMPUTER_BETA_FLAG in client.beta_calls[0]["betas"]
    # The computer tool was offered.
    assert any(t.get("name") == "computer" for t in client.beta_calls[0]["tools"])
    # The action is surfaced for the UI.
    assert result.actions[0]["action"] == "computer:screenshot"


def test_no_computer_use_stays_on_plain_endpoint():
    resp = SimpleNamespace(content=[_text("hi")], stop_reason="end_turn")
    client = BetaFakeClient([resp])
    brain = DonaldBrain(
        client=client, hermes=Hermes(dry_run=True), personality_text="P"
    )
    brain.take_turn("hey")
    assert client.calls and not client.beta_calls
    assert not any(t.get("name") == "computer" for t in client.calls[0]["tools"])
