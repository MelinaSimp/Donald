"""Tests for the pure self-knowledge generators and the renderer."""

from __future__ import annotations

from donald.integrations import Integration
from donald.self_knowledge import generators, render
from donald.self_knowledge.parser import SelfKnowledgeDoc
from donald.subagents import SubAgent
from donald.tools import BaseTool, ToolRegistry


def _fixture_registry() -> ToolRegistry:
    reg = ToolRegistry()

    class A(BaseTool):
        name = "alpha"
        description = "First tool."
        category = "utility"

    class B(BaseTool):
        name = "beta"
        description = "Second tool."
        category = "research"

    reg.register(A())
    reg.register(B())
    return reg


def test_render_capabilities_table():
    out = generators.render_capabilities(_fixture_registry())
    assert "| Tool | Description | Category |" in out
    assert "| `alpha` | First tool. | utility |" in out
    assert "| `beta` | Second tool. | research |" in out
    # Sorted: alpha before beta.
    assert out.index("alpha") < out.index("beta")


def test_render_integrations_includes_status(monkeypatch):
    monkeypatch.delenv("DEMO_KEY", raising=False)
    integs = [Integration("Demo", "Does demo things.", "DEMO_KEY", "llm")]
    out = generators.render_integrations(integs)
    assert "| Demo | Does demo things. | llm | not configured |" in out
    monkeypatch.setenv("DEMO_KEY", "x")
    out2 = generators.render_integrations(integs)
    assert "configured" in out2 and "not configured" not in out2


def test_render_subagents():
    subs = [SubAgent("scout", "Looks around.", ("alpha", "beta"))]
    out = generators.render_subagents(subs)
    assert "| `scout` | Looks around. | `alpha`, `beta` |" in out


def test_render_recent_activity_empty_and_full():
    assert "No commits" in generators.render_recent_activity([])
    out = generators.render_recent_activity([("2026-06-25", "Do a thing")])
    assert "- `2026-06-25` — Do a thing" in out


def test_table_empty_is_none():
    assert generators._table(("A",), []) == "_none_"


def test_render_doc_replaces_known_blocks_and_keeps_prose():
    text = (
        "intro\n"
        "<!-- AUTO-START: capabilities -->\nold\n<!-- AUTO-END: capabilities -->\n"
        "middle\n"
    )
    specs = [render.BlockSpec("capabilities", "_note._", lambda: "FRESH")]
    out = render.render_doc(text, specs)
    assert "intro" in out and "middle" in out
    assert "_note._\n\nFRESH" in out
    assert "old" not in out


def test_render_doc_degrades_on_generator_failure():
    text = "<!-- AUTO-START: capabilities -->\nx\n<!-- AUTO-END: capabilities -->\n"

    def boom() -> str:
        raise ImportError("registry gone")

    specs = [render.BlockSpec("capabilities", "_note._", boom)]
    out = render.render_doc(text, specs)
    assert render.UNAVAILABLE in out


def test_render_doc_default_specs_against_real_sources():
    # End-to-end: real registry/integrations/subagents, no placeholders.
    text = SelfKnowledgeDoc.parse(
        (render.doc_path().read_text(encoding="utf-8"))
    ).serialize()
    out = render.render_doc(text)
    assert render.UNAVAILABLE not in out
    assert "`calculator`" in out  # from the real registry
    assert "Anthropic" in out  # from the real integrations
    assert "`researcher`" in out  # from the real sub-agents
