"""3.3 - Kill switch.

Threat: mid-incident, you need a single "stop this thing" button. ``is_active()``
reads an env var (default ``AGENT_KILL_SWITCH``); when truthy, every tool
dispatch should short-circuit and the scheduler tick should skip itself.

    from security.killswitch import is_active, kill_switch_response

    if is_active():
        return kill_switch_response()
    ... dispatch the tool ...

Flip it with one secrets-manager command; it takes effect on the next tool
dispatch. The audit shield (3.5) reports an active switch as severity
``critical``.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

DEFAULT_ENV_VAR = "AGENT_KILL_SWITCH"
_TRUTHY = {"true", "1", "yes", "on"}


def is_active(
    env_var: str = DEFAULT_ENV_VAR,
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """True if the kill-switch env var is set to a truthy value."""
    src = os.environ if environ is None else environ
    return str(src.get(env_var, "")).strip().lower() in _TRUTHY


def kill_switch_response(
    agent_name: str = "agent",
    env_var: str = DEFAULT_ENV_VAR,
) -> dict:
    """The structured response every tool returns while the switch is active."""
    return {
        "status": "kill_switch_active",
        "message": (
            f"{agent_name} is paused. Set {env_var}=false to resume."
        ),
    }
