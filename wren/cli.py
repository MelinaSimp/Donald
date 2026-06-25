"""Command-line entry points.

  python -m wren.cli            # text chat (default) — the brain, alive forever
  python -m wren.cli chat       # same
  python -m wren.cli voice      # push-to-talk voice (Tier 3)
  python -m wren.cli heartbeat  # run the background loop (Tier 5)
  python -m wren.cli inbox      # show held notices; `inbox clear [id]` to dismiss
  python -m wren.cli kill       # pause all proactive behaviour (kill switch)
  python -m wren.cli unkill     # resume
  python -m wren.cli cost       # session/lifetime model cost from the audit log
  python -m wren.cli send-test  # send a test email through the gated path (no model)
"""
from __future__ import annotations

import sys

from .config import Config
from .safety import set_paused


def cmd_chat() -> None:
    from .app import build_app

    app = build_app()
    name = app.config.get("assistant.name", "Wren")

    # Tier 5: catch up on anything held while you were away.
    pending = app.inbox.pending()
    if pending:
        print(f"📥 {len(pending)} notice(s) waiting:")
        for n in pending:
            print(f"   • [{n['id']}] {n['text']}")
        print("   (clear with: python -m wren.cli inbox clear)\n")

    # Tier 4: greet like it knows you, if it does.
    facts = app.memory.all()
    hello = f"{name} ▷ Hi" + ("" if not facts else " — good to see you again") + "."
    print(hello)
    print("   (type 'q' to quit)\n")

    while True:
        try:
            text = input("you ▷ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in ("q", "quit", "exit"):
            break
        print(f"{name} ▷ ", end="", flush=True)
        app.agent.respond(text, on_text=lambda t: print(t, end="", flush=True), source="text")
        print("\n")

    print(app.audit.cost_line())


def cmd_voice() -> None:
    from .app import build_app
    from .voice.loop import run_voice

    run_voice(build_app())


def cmd_heartbeat() -> None:
    from .app import build_app
    from .heartbeat import Heartbeat

    app = build_app()
    hb = Heartbeat(app.config, app.ctx.reminders, app.inbox, app.audit)
    hb.run_forever()


def cmd_inbox(args: list[str]) -> None:
    from .app import build_app

    app = build_app()
    if args and args[0] == "clear":
        target = int(args[1]) if len(args) > 1 else None
        n = app.inbox.dismiss(target)
        print(f"Cleared {n} notice(s).")
        return
    pending = app.inbox.pending()
    if not pending:
        print("Inbox empty.")
        return
    for n in pending:
        print(f"[{n['id']}] ({n['level']}) {n['ts']}  {n['text']}")


def cmd_kill(paused: bool) -> None:
    config = Config.load()
    set_paused(config, paused)
    print("Proactive behaviour paused." if paused else "Proactive behaviour resumed.")


def cmd_send_test() -> None:
    """Send a test email through the exact gated path send_message uses — without
    the model — to confirm SMTP creds and the confirmation gate work."""
    from .app import build_app

    app = build_app()
    if app.ctx.mailer is None:
        print("Email isn't configured. Set email.smtp_host / email.from_addr in "
              "config.yaml and SMTP_USERNAME / SMTP_PASSWORD in .env.")
        return
    to = input("To: ").strip()
    subject = input("Subject: ").strip()
    body = input("Body: ").strip()
    # Same gate + audit path the model takes — console_gate will prompt y/N.
    result = app.agent.invoke_tool(
        "send_message", {"to": to, "subject": subject, "body": body}, source="send-test"
    )
    print(result)


def cmd_cost() -> None:
    import json

    config = Config.load()
    path = config.resolve_path("safety.audit_log", "data/audit.log")
    total = 0.0
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                total += float(json.loads(line).get("cost_usd", 0) or 0)
            except (json.JSONDecodeError, ValueError):
                continue
    print(f"~${total:.4f} spent on the model (all time, from audit log)")


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "chat"
    rest = argv[1:]
    if cmd == "chat":
        cmd_chat()
    elif cmd == "voice":
        cmd_voice()
    elif cmd == "heartbeat":
        cmd_heartbeat()
    elif cmd == "inbox":
        cmd_inbox(rest)
    elif cmd == "kill":
        cmd_kill(True)
    elif cmd == "unkill":
        cmd_kill(False)
    elif cmd == "send-test":
        cmd_send_test()
    elif cmd == "cost":
        cmd_cost()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
