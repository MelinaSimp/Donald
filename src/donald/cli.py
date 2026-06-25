"""Command-line entry point for Donald."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import AGENT_DESCRIPTION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="donald", description=AGENT_DESCRIPTION)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("prompt", help="Print the assembled system prompt")

    sk = sub.add_parser("self-knowledge", help="Manage the self-knowledge document")
    mode = sk.add_mutually_exclusive_group(required=True)
    mode.add_argument("--render", action="store_true", help="Print the rendered doc (no write)")
    mode.add_argument("--refresh", action="store_true", help="Regenerate AUTO blocks on disk")
    mode.add_argument("--check", action="store_true", help="Report drift in hand-written prose")
    sk.add_argument(
        "--strict",
        action="store_true",
        help="With --check, exit non-zero if any drift is found",
    )
    return parser


def _run_self_knowledge(args: argparse.Namespace) -> int:
    # Imported lazily so `donald prompt` stays fast and dependency-light.
    from .self_knowledge import check_drift, refresh_file, render_file

    if args.render:
        sys.stdout.write(render_file())
        return 0

    if args.refresh:
        changed = refresh_file()
        print("self-knowledge: doc updated" if changed else "self-knowledge: already up to date")
        return 0

    if args.check:
        findings = check_drift()
        if not findings:
            print("self-knowledge: no drift found")
            return 0
        label = "ERROR" if args.strict else "WARN"
        for f in findings:
            print(f"{label} [{f.kind}] line {f.location_in_doc}: {f.reference} — {f.reason}")
        print(f"self-knowledge: {len(findings)} drift finding(s)")
        return 1 if args.strict else 0

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "prompt":
        from .prompt import build_system_prompt

        print(build_system_prompt())
        return 0
    if args.command == "self-knowledge":
        return _run_self_knowledge(args)

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
