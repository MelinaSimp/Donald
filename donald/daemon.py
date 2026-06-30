"""Tier 4 entry point — run Donald with the proactive loop alongside chat.

`donald daemon` starts the normal text conversation *and* the background loop.
While you chat (or sit idle), Donald checks its triggers on an interval and
interjects when something is due. The loop only ever *reads* state and speaks;
it never takes a mutating action unattended (see Tier 5).
"""

from __future__ import annotations

import sys

from .app import build
from .conversation import run_repl
from .proactive import ProactiveLoop


def run_daemon() -> None:
    donald = build()
    memory = donald.registry.context.memory
    config = donald.config

    def notify(message: str) -> None:
        # \a rings the terminal bell; printed above the input prompt.
        print(f"\n\a\033[36m🔔 Donald: {message}\033[0m", file=sys.stderr)

    loop = ProactiveLoop(
        memory=memory,
        notifier=notify,
        interval=config.proactive_interval,
    )

    if config.proactive_enabled:
        loop.start()
        banner = (
            f"Proactive loop ON (checking every {config.proactive_interval}s). "
            "Donald may reach out on its own."
        )
    else:
        banner = (
            "Proactive loop is OFF. Set DONALD_PROACTIVE=on in .env to let "
            "Donald reach out first."
        )
    print(banner)

    try:
        run_repl(donald.agent, greeting="Donald is here, and watching the clock.")
    finally:
        loop.stop()
