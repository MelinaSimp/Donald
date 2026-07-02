"""Shared test fakes and fixtures — no network, no API key.

The agent loop is driven by an LLM; tests inject a scripted fake so the loop's
control flow (bounded iteration, tool dispatch, handoff capture) is exercised
deterministically without touching the Messages API.

Prism tests use a throwaway project resolvable via PRISM_PROJECTS_BASE.
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any, Callable

import pytest


def _text_block(text: str):
    return types.SimpleNamespace(type="text", text=text)


def _tool_use_block(name: str, tool_input: dict[str, Any], block_id: str):
    return types.SimpleNamespace(
        type="tool_use", name=name, input=tool_input, id=block_id
    )


def text_response(text: str):
    """A terminal assistant turn (stop_reason end_turn)."""
    return types.SimpleNamespace(content=[_text_block(text)], stop_reason="end_turn")


def tool_response(name: str, tool_input: dict[str, Any], block_id: str = "tu_x"):
    """An assistant turn that requests one tool call (stop_reason tool_use)."""
    return types.SimpleNamespace(
        content=[_tool_use_block(name, tool_input, block_id)], stop_reason="tool_use"
    )


class ScriptedLLM:
    """An LLM whose `complete` returns scripted responses in order.

    If the script runs out, it falls back to `default` (so a loop that asks for
    a tool forever can be bounded by the agent's max_iterations).
    """

    def __init__(self, script: list, default=None) -> None:
        self._script = list(script)
        self._default = default if default is not None else text_response("done")
        self.calls = 0

    def complete(self, **_kwargs):
        self.calls += 1
        if self._script:
            return self._script.pop(0)
        return self._default


class EchoLLM:
    """Always finishes immediately, echoing the task — for runtime tests."""

    def complete(self, *, model, messages, **_kwargs):
        return text_response(f"[{model}] handled: {messages[-1]['content']}")


def callable_returning(fn: Callable[..., Any]):
    """Wrap a plain function as an object with a `.complete` attribute."""
    return types.SimpleNamespace(complete=fn)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Create a fresh project dir and make Prism resolve `<slug>` to it.

    Uses PRISM_PROJECTS_BASE convention so we never touch the real registry.
    Returns (slug, root_path).
    """
    base = tmp_path / "projects"
    base.mkdir()
    slug = "test-app"
    root = base / slug
    root.mkdir()
    # Minimal repo signal for the bootstrap scan.
    (root / "package.json").write_text(
        json.dumps({"name": slug, "description": "A test app for Prism.",
                    "dependencies": {"next": "15.0.0", "react": "19.0.0"}})
    )
    (root / "README.md").write_text("# Test App\n\nA delightful test application.\n")

    monkeypatch.setenv("PRISM_PROJECTS_BASE", str(base))
    monkeypatch.setenv("PRISM_REGISTRY", str(tmp_path / "no-registry.json"))
    return slug, root
