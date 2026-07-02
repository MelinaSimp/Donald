"""Tests for the dashboard state tracking and API."""

from gateway.dashboard_state import DashboardAction, DashboardState, get_dashboard_state


def test_dashboard_state_creation():
    """Test creating a DashboardState instance."""
    state = DashboardState(max_actions=50)
    assert state.max_actions == 50
    assert len(state.actions) == 0
    assert state.session_turn_count == 0
    assert state.hermes_action_count == 0
    assert not state.is_paused


def test_dashboard_record_event():
    """Test recording events to the dashboard."""
    state = DashboardState()

    # Record a tool call
    event = {
        "type": "tool_call",
        "name": "hermes",
        "task": "list files in /tmp",
        "reason": "exploring the filesystem",
    }
    state.record_event("session_1", event)

    assert len(state.actions) == 1
    assert state.actions[0].action_type == "tool_call"
    assert state.actions[0].status == "pending"
    assert state.actions[0].task == "list files in /tmp"

    # Record a tool result
    event = {
        "type": "tool_result",
        "name": "hermes",
        "error": None,
        "preview": "file1.txt\nfile2.txt",
    }
    state.record_event("session_1", event)

    # Status should be updated
    assert state.actions[0].status == "ok"
    assert state.actions[0].preview == "file1.txt\nfile2.txt"

    # Record a final event
    event = {
        "type": "final",
        "text": "Here are the files in /tmp",
    }
    state.record_event("session_1", event)

    assert state.session_turn_count == 1
    assert state.last_response == "Here are the files in /tmp"


def test_dashboard_record_declined():
    """Test recording a declined action."""
    state = DashboardState()

    state.record_event("session_1", {
        "type": "tool_call",
        "name": "hermes",
        "task": "delete important file",
        "reason": "user asked",
    })

    state.record_event("session_1", {
        "type": "tool_result",
        "name": "hermes",
        "declined": True,
    })

    assert state.actions[0].status == "declined"


def test_dashboard_pause_resume():
    """Test pause and resume functionality."""
    state = DashboardState()
    assert not state.is_paused

    state.pause()
    assert state.is_paused

    state.resume()
    assert not state.is_paused


def test_dashboard_snapshot():
    """Test the snapshot method."""
    state = DashboardState()
    state.set_user_message("what's the time?")
    state.record_event("session_1", {
        "type": "tool_call",
        "name": "hermes",
        "task": "get current time",
    })
    state.record_event("session_1", {
        "type": "tool_result",
        "name": "hermes",
        "preview": "2025-01-15 14:30:00",
    })
    state.record_event("session_1", {
        "type": "final",
        "text": "It's 2:30 PM",
    })

    snapshot = state.snapshot()

    assert snapshot["paused"] is False
    assert snapshot["turn_count"] == 1
    assert snapshot["hermes_actions"] == 1
    assert snapshot["last_user_message"] == "what's the time?"
    assert snapshot["last_response"] == "It's 2:30 PM"
    assert len(snapshot["actions"]) == 1
    assert snapshot["actions"][0]["status"] == "ok"


def test_dashboard_global_instance():
    """Test the global dashboard state instance."""
    state = get_dashboard_state()
    assert isinstance(state, DashboardState)

    # Should return the same instance
    state2 = get_dashboard_state()
    assert state is state2


def test_dashboard_action_to_dict():
    """Test DashboardAction.to_dict()."""
    action = DashboardAction(
        timestamp=1000000.0,
        action_type="tool_call",
        name="hermes",
        status="ok",
        task="test task",
        reason="testing",
        preview="result",
        error=None,
    )

    d = action.to_dict()
    assert d["action_type"] == "tool_call"
    assert d["name"] == "hermes"
    assert d["status"] == "ok"
    assert d["task"] == "test task"
    assert d["preview"] == "result"


def test_dashboard_max_actions_bounded():
    """Test that the action deque is bounded."""
    state = DashboardState(max_actions=5)

    for i in range(10):
        state.record_event("session_1", {
            "type": "tool_call",
            "name": "hermes",
            "task": f"task {i}",
        })

    # Should only have the last 5
    assert len(state.actions) == 5
    assert state.actions[0].task == "task 5"
    assert state.actions[-1].task == "task 9"
