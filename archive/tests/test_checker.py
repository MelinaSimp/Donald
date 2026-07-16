"""Tests for the self-knowledge drift checker."""

from __future__ import annotations

from pathlib import Path

from donald.self_knowledge import checker
from donald.self_knowledge.checker import (
    CodeIndex,
    check_drift,
    extract_references,
    load_allowlist,
)
from donald.self_knowledge.parser import SelfKnowledgeDoc

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_real_doc_has_no_drift():
    # The committed doc's hand-written references must all resolve.
    assert check_drift(REPO_ROOT) == []


def test_extract_references_classifies_kinds():
    text = (
        "See `src/donald/prompt.py` and `README.md`.\n"
        "Call `build_system_prompt` or `ToolRegistry.register`.\n"
        "Use the `web_search` tool. Ignore `not configured` prose.\n"
        "<!-- AUTO-START: x -->\n`inside.block` should be ignored\n<!-- AUTO-END: x -->\n"
    )
    doc = SelfKnowledgeDoc.parse(text)
    refs = extract_references(doc)
    kinds = {ref: kind for kind, ref, _ in refs}
    assert kinds["src/donald/prompt.py"] == "file"
    assert kinds["README.md"] == "file"
    assert kinds["build_system_prompt"] == "name"
    assert kinds["ToolRegistry.register"] == "symbol"
    assert kinds["web_search"] == "name"
    # Multi-word prose in backticks is not a reference.
    assert "not configured" not in kinds
    # References inside AUTO blocks are skipped.
    assert "inside.block" not in kinds


def test_check_flags_missing_file_and_symbol():
    text = (
        "Broken path `src/donald/does_not_exist.py`.\n"
        "Broken symbol `NoSuchClass.no_method`.\n"
        "Broken name `not_a_real_tool`.\n"
    )
    findings = check_drift(REPO_ROOT, doc_text=text)
    refs = {f.reference: f for f in findings}
    assert refs["src/donald/does_not_exist.py"].kind == "file"
    assert refs["NoSuchClass.no_method"].kind == "symbol"
    assert refs["not_a_real_tool"].kind == "name"
    # Line numbers are reported.
    assert refs["src/donald/does_not_exist.py"].location_in_doc == 1


def test_allowlist_suppresses_findings(tmp_path, monkeypatch):
    text = "Planned `future_tool` not built yet.\n"
    # No allowlist -> flagged.
    assert any(f.reference == "future_tool" for f in check_drift(REPO_ROOT, doc_text=text))

    # With allowlist entry -> suppressed.
    allow = tmp_path / "allow.txt"
    allow.write_text("future_tool\n# a comment\n", encoding="utf-8")
    monkeypatch.setattr(checker, "allowlist_path", lambda root=None: allow)
    assert not any(f.reference == "future_tool" for f in check_drift(REPO_ROOT, doc_text=text))


def test_load_allowlist_ignores_comments(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("# comment\nfoo\n\n  bar  \n", encoding="utf-8")
    assert load_allowlist(p) == {"foo", "bar"}


def test_build_symbol_index_finds_known_symbols():
    index = checker.build_symbol_index(REPO_ROOT / "src")
    assert "build_system_prompt" in index.names
    assert "ToolRegistry" in index.names
    assert "ToolRegistry.register" in index.dotted


def test_load_allowlist_missing_is_empty(tmp_path):
    assert load_allowlist(tmp_path / "nope.txt") == set()
