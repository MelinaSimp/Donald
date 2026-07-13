from __future__ import annotations

import pytest

from agent_factory.models import (
    InvalidTransition,
    State,
    assert_transition,
    slugify,
)


def test_legal_transitions():
    assert_transition(State.PENDING, State.RESEARCHING)
    assert_transition(State.AWAITING_APPROVAL, State.APPROVED)
    assert_transition(State.AWAITING_APPROVAL, State.WRITING_PROMPT)  # revision rollback


def test_illegal_transition_raises():
    with pytest.raises(InvalidTransition):
        assert_transition(State.PENDING, State.APPROVED)
    with pytest.raises(InvalidTransition):
        assert_transition(State.APPROVED, State.PENDING)  # terminal


def test_terminal_states_have_no_exits():
    for term in (State.APPROVED, State.REJECTED, State.FAILED):
        for dst in State:
            with pytest.raises(InvalidTransition):
                assert_transition(term, dst)


def test_slugify():
    assert slugify("Doc Summarizer") == "doc_summarizer"
    assert slugify("  Atlas!! ") == "atlas"
    assert slugify("") == "agent"
