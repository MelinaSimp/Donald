"""Tiny CLI for Prism: bootstrap, scaffold, and dispatch design tasks.

    prism bootstrap <slug> [--path DIR]
    prism scaffold  <slug>
    prism dispatch  <slug> "design the hero" [--path DIR]
    prism serve     [--host H] [--port N]

Live dispatch needs ANTHROPIC_API_KEY (and, for images, GEMINI_API_KEY); the
bootstrap/scaffold subcommands need neither.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="prism", description="Prism head-of-design agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_boot = sub.add_parser("bootstrap", help="create concrete design.md + brief.md")
    p_boot.add_argument("slug")
    p_boot.add_argument("--path", default=None, help="register slug -> this path first")

    p_scaf = sub.add_parser("scaffold", help="create the Next.js preview app")
    p_scaf.add_argument("slug")

    p_disp = sub.add_parser("dispatch", help="run a design task end to end")
    p_disp.add_argument("slug")
    p_disp.add_argument("task")
    p_disp.add_argument("--path", default=None)

    p_serve = sub.add_parser("serve", help="serve preview exports")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.cmd == "bootstrap":
        from . import bootstrap, docs
        if args.path:
            docs.register_project(args.slug, args.path)
        res = bootstrap.bootstrap_project(args.slug)
        print(f"design.md {'created' if res.created_design else 'exists'} -> {res.design_path}")
        print(f"brief.md  {'created' if res.created_brief else 'exists'} -> {res.brief_path}")
        return 0

    if args.cmd == "scaffold":
        from . import orchestrator
        created = orchestrator.ensure_scaffold(args.slug)
        print("scaffold created" if created else "scaffold already present")
        return 0

    if args.cmd == "dispatch":
        from . import orchestrator
        outcome = orchestrator.dispatch_design_task(
            args.slug, args.task, register_path=args.path,
            on_event=lambda e: print(f"[CC] {e.get('type','')}", file=sys.stderr),
        )
        print(outcome.result.final_text or "(no final text)")
        return 0 if not any(
            isinstance(te.output, dict) and not te.output.get("ok", True)
            for te in outcome.result.tool_events
        ) else 1

    if args.cmd == "serve":
        import uvicorn  # type: ignore
        from . import serving
        uvicorn.run(serving.create_app(), host=args.host, port=args.port)
        return 0

    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
