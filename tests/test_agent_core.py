"""Tests for the core agent scaffold: tools, integrations, sub-agents, prompt."""

from __future__ import annotations

import pytest

from donald import AGENT_NAME
from donald.integrations import all_integrations
from donald.prompt import build_system_prompt
from donald.subagents import all_subagents
from donald.tools import BaseTool, ToolRegistry, build_default_registry


def test_default_registry_has_expected_tools():
    registry = build_default_registry()
    assert {"echo", "calculator", "web_search", "send_email", "clock"} <= set(registry.names())
    assert len(registry) >= 5


def test_registry_rejects_duplicates_and_empty_names():
    registry = ToolRegistry()

    class Nameless(BaseTool):
        name = ""

    with pytest.raises(ValueError):
        registry.register(Nameless())

    class Dup(BaseTool):
        name = "dup"

    registry.register(Dup())
    with pytest.raises(ValueError):
        registry.register(Dup())


def test_registry_tools_are_sorted():
    registry = build_default_registry()
    names = [t.name for t in registry.tools()]
    assert names == sorted(names)


def test_calculator_executes_and_rejects_bad_input():
    calc = build_default_registry().get("calculator")
    assert calc.execute(expression="2 + 3 * 4") == 14.0
    with pytest.raises(ValueError):
        calc.execute(expression="__import__('os')")


def test_integrations_expose_env_and_purpose():
    integrations = all_integrations()
    names = {i.name for i in integrations}
    assert {"Anthropic", "SMTP", "Tavily"} <= names
    for integ in integrations:
        assert integ.env_var
        assert integ.purpose


def test_subagents_reference_real_tools():
    registry = build_default_registry()
    for sub in all_subagents():
        assert sub.role
        for tool_name in sub.tools:
            assert tool_name in registry, f"{sub.name} references unknown tool {tool_name}"


def test_system_prompt_mentions_tools():
    prompt = build_system_prompt()
    assert "Donald" in prompt
    assert "echo" in prompt
    assert AGENT_NAME == "donald"
