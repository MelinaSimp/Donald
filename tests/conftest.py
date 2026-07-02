"""Shared fixtures: isolate HOME (memory/config) and CWD (file tools) per test."""

import importlib
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
def home(tmp_path, monkeypatch):
    """Point ~/.donald at a throwaway dir so tests never touch the real home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Reload modules that bind paths at import time off the patched HOME.
    import donald.memory as memory

    importlib.reload(memory)
    return tmp_path


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Run inside a throwaway working directory for the file tools."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
