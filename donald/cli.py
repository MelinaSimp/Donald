"""Donald's command line entry point.

  donald            → text conversation loop (Tier 0/1/3/5)
  donald voice      → talk to Donald with your voice (Tier 2)
  donald daemon     → run with the proactive background loop on (Tier 4)
  donald tools      → list the tools Donald has
  donald doctor     → check which tiers are configured/ready
"""

from __future__ import annotations

import sys

from .app import build
from .config import Config


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "chat"

    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    if cmd == "doctor":
        return _doctor()

    if cmd == "tools":
        donald = build()
        print("Donald's tools:")
        for name in donald.registry.names():
            print(f"  - {name}")
        return 0

    if cmd == "voice":
        from .voice import run_voice

        donald = build()
        run_voice(donald)
        return 0

    if cmd == "daemon":
        from .daemon import run_daemon

        run_daemon()
        return 0

    # Default: text chat.
    from .conversation import run_repl

    donald = build()
    greeting = (
        "Donald online (mock brain — set ANTHROPIC_API_KEY for the real one)."
        if donald.config.brain == "mock"
        else "Donald online. How can I help?"
    )
    run_repl(donald.agent, greeting=greeting)
    return 0


def _doctor() -> int:
    cfg = Config.load()
    cfg.ensure_dirs()

    def status(ok: bool) -> str:
        return "\033[32mready\033[0m" if ok else "\033[33mnot configured\033[0m"

    print("Donald readiness check\n")
    print(f"  Tier 0  text loop        \033[32mready\033[0m")
    print(f"  Tier 1  tools            \033[32mready\033[0m")
    print(
        f"  Brain                    "
        f"{'claude' if cfg.brain == 'claude' else 'mock (no ANTHROPIC_API_KEY)'}"
    )
    print(f"  Tier 2  speech-to-text   {status(bool(cfg.deepgram_api_key))} (Deepgram)")
    print(f"  Tier 2  text-to-speech   {status(bool(cfg.elevenlabs_api_key))} (ElevenLabs)")
    print(f"  Tier 3  memory (SQLite)  \033[32mready\033[0m  → {cfg.db_path}")
    print(f"  Tier 4  proactive loop   {'on' if cfg.proactive_enabled else 'off'}")
    print(f"  Tier 5  safety rails     \033[32mready\033[0m")
    print(f"\n  Workspace: {cfg.workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
