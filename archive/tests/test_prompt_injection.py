"""Tests for self-knowledge injection into the system prompt (Phase 5)."""

from __future__ import annotations

from donald.prompt import SelfKnowledgeFlavor, build_system_prompt
from donald.self_knowledge.summary import extract_section, slim_summary
from donald.tools import BaseTool, ToolRegistry, build_default_registry

DOC = (
    "# Donald — Self-Knowledge\n\n"
    "## Identity\n\nDonald is a helpful assistant.\n\n"
    "## Core principles\n\n- Be honest.\n\n"
    "## Capabilities at a glance\n\nignored auto stuff\n"
)


def _registry_with(*names: str) -> ToolRegistry:
    reg = ToolRegistry()
    for n in names:
        tool = type(f"T_{n}", (BaseTool,), {"name": n, "description": f"{n} tool"})()
        reg.register(tool)
    return reg


def test_extract_section():
    assert extract_section(DOC, "Identity") == "Donald is a helpful assistant."
    assert "Be honest." in extract_section(DOC, "Core principles")
    assert extract_section(DOC, "Nope") == ""


def test_slim_summary_has_identity_principles_and_names():
    reg = _registry_with("alpha", "beta")
    out = slim_summary(reg, DOC)
    assert "Donald is a helpful assistant." in out
    assert "Be honest." in out
    assert "alpha, beta" in out
    # Slim must not embed full tool descriptions.
    assert "alpha tool" not in out


def test_default_flavor_is_slim_and_injects_self_knowledge():
    prompt = build_system_prompt(doc_text=DOC)
    assert "# Self-knowledge" in prompt
    assert "Donald is a helpful assistant." in prompt


def test_flavor_none_omits_block():
    prompt = build_system_prompt(self_knowledge=SelfKnowledgeFlavor.NONE, doc_text=DOC)
    assert "# Self-knowledge" not in prompt


def test_env_var_controls_flavor(monkeypatch):
    monkeypatch.setenv("DONALD_SELF_KNOWLEDGE", "none")
    assert "# Self-knowledge" not in build_system_prompt(doc_text=DOC)
    monkeypatch.setenv("DONALD_SELF_KNOWLEDGE", "slim")
    assert "# Self-knowledge" in build_system_prompt(doc_text=DOC)


def test_prompt_reflects_added_then_removed_tool():
    # A recently-added tool is mentioned...
    with_clock = build_system_prompt(registry=build_default_registry(), doc_text=DOC)
    assert "clock" in with_clock
    # ...and a registry without it no longer mentions it (same source of truth).
    without_clock = build_system_prompt(registry=_registry_with("echo"), doc_text=DOC)
    assert "clock" not in without_clock


def test_missing_doc_degrades_gracefully():
    # Empty doc text: slim still lists capabilities, no crash.
    out = build_system_prompt(registry=_registry_with("only"), doc_text="")
    assert "only" in out
