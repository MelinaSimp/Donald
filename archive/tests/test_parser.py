"""Tests for the self-knowledge block parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from donald.self_knowledge.parser import SelfKnowledgeDoc

DOC = (
    "# Title\n\n"
    "Hand-written intro.\n\n"
    "<!-- AUTO-START: capabilities -->\n"
    "old caps\n"
    "<!-- AUTO-END: capabilities -->\n\n"
    "Hand-written middle that must survive.\n\n"
    "<!-- AUTO-START: integrations -->\n"
    "old integ\n"
    "<!-- AUTO-END: integrations -->\n\n"
    "Hand-written outro.\n"
)


def test_roundtrip_is_a_noop():
    doc = SelfKnowledgeDoc.parse(DOC)
    assert doc.serialize() == DOC


def test_block_names_in_order():
    doc = SelfKnowledgeDoc.parse(DOC)
    assert doc.block_names() == ["capabilities", "integrations"]


def test_replace_preserves_handwritten_between_blocks():
    doc = SelfKnowledgeDoc.parse(DOC)
    doc.replace_block("capabilities", "NEW CAPS")
    out = doc.serialize()
    # Hand-written content untouched.
    assert "Hand-written intro." in out
    assert "Hand-written middle that must survive." in out
    assert "Hand-written outro." in out
    # The other AUTO block untouched.
    assert "old integ" in out
    # The replaced block updated, markers intact.
    assert "<!-- AUTO-START: capabilities -->\nNEW CAPS\n<!-- AUTO-END: capabilities -->" in out
    assert "old caps" not in out


def test_replace_round_trips_after_reparse():
    doc = SelfKnowledgeDoc.parse(DOC)
    doc.replace_block("capabilities", "NEW CAPS")
    once = doc.serialize()
    # Re-parsing and replacing with identical content is stable.
    doc2 = SelfKnowledgeDoc.parse(once)
    doc2.replace_block("capabilities", "NEW CAPS")
    assert doc2.serialize() == once


def test_crlf_is_preserved_and_used_for_replacement():
    crlf = DOC.replace("\n", "\r\n")
    doc = SelfKnowledgeDoc.parse(crlf)
    assert doc.serialize() == crlf
    doc.replace_block("capabilities", "line1\nline2")
    out = doc.serialize()
    assert "\r\nline1\r\nline2\r\n" in out
    assert "\n" not in out.replace("\r\n", "")  # no lone LFs introduced


def test_duplicate_block_names_rejected():
    bad = (
        "<!-- AUTO-START: x -->\na\n<!-- AUTO-END: x -->\n"
        "<!-- AUTO-START: x -->\nb\n<!-- AUTO-END: x -->\n"
    )
    with pytest.raises(ValueError):
        SelfKnowledgeDoc.parse(bad)


def test_unbalanced_marker_rejected():
    bad = "intro\n<!-- AUTO-START: x -->\nno end here\n"
    with pytest.raises(ValueError):
        SelfKnowledgeDoc.parse(bad)


def test_unknown_block_lookup_raises():
    doc = SelfKnowledgeDoc.parse(DOC)
    with pytest.raises(KeyError):
        doc.get_block_body("nope")


def test_real_doc_on_disk_round_trips():
    path = Path(__file__).resolve().parents[1] / "context" / "self" / "donald.md"
    text = path.read_text(encoding="utf-8")
    doc = SelfKnowledgeDoc.parse(text)
    assert doc.serialize() == text
    assert "capabilities" in doc.block_names()
