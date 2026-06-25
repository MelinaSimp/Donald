"""Command-line entry point for Donald."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import AGENT_DESCRIPTION
from .prompt import build_system_prompt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="donald", description=AGENT_DESCRIPTION)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("prompt", help="Print the assembled system prompt")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "prompt":
        print(build_system_prompt())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
