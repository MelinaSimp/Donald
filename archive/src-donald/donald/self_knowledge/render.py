"""Wire the generators to AUTO block names and render the whole document.

The renderer is the only impure layer: it reaches into the live
registration sites (the tool registry, the integrations list, the
sub-agent list, git history), hands those snapshots to the pure
generators, and writes the results back into the document.

If a generator's source can't be reached (import error, not a git
checkout, etc.) the block is filled with a clearly-marked placeholder
rather than crashing — so a refresh never breaks a commit.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import generators
from .parser import SelfKnowledgeDoc
from .paths import doc_path, find_repo_root

UNAVAILABLE = "_unavailable, regenerate manually_"
RECENT_ACTIVITY_DAYS = 14


@dataclass
class BlockSpec:
    """Binds an AUTO block name to a note and a content producer."""

    name: str
    note: str
    produce: Callable[[], str]


def collect_recent_commits(
    repo_root: Optional[Path] = None, days: int = RECENT_ACTIVITY_DAYS
) -> List[Tuple[str, str]]:
    """Return (date, subject) pairs for commits in the last ``days`` days."""
    root = repo_root or find_repo_root()
    out = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            f"--since={days} days ago",
            "--date=short",
            "--pretty=format:%ad\x1f%s",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    commits: List[Tuple[str, str]] = []
    for line in out.stdout.splitlines():
        if "\x1f" in line:
            date, subject = line.split("\x1f", 1)
            commits.append((date, subject))
    return commits


def default_specs() -> List[BlockSpec]:
    """The canonical block specs, each reading from the live source."""
    # Imports are deferred into the producers so an import failure in one
    # source degrades only that block.
    def caps() -> str:
        from ..tools import build_default_registry

        return generators.render_capabilities(build_default_registry())

    def integ() -> str:
        from ..integrations import all_integrations

        return generators.render_integrations(all_integrations())

    def subs() -> str:
        from ..subagents import all_subagents

        return generators.render_subagents(all_subagents())

    def recent() -> str:
        return generators.render_recent_activity(collect_recent_commits())

    return [
        BlockSpec("capabilities", "_Generated from the tool registry._", caps),
        BlockSpec("integrations", "_Generated from the integrations module._", integ),
        BlockSpec("subagents", "_Generated from the sub-agent registry._", subs),
        BlockSpec(
            "recent-activity",
            f"_Generated from git log (last {RECENT_ACTIVITY_DAYS} days)._",
            recent,
        ),
    ]


def render_doc(text: str, specs: Optional[List[BlockSpec]] = None) -> str:
    """Return ``text`` with every known AUTO block refreshed."""
    specs = specs if specs is not None else default_specs()
    doc = SelfKnowledgeDoc.parse(text)
    present = set(doc.block_names())
    for spec in specs:
        if spec.name not in present:
            continue
        try:
            content = spec.produce()
            body = f"{spec.note}\n\n{content}"
        except Exception:  # noqa: BLE001 - never let a refresh break a commit
            body = UNAVAILABLE
        doc.replace_block(spec.name, body)
    return doc.serialize()


def render_file(path: Optional[Path] = None, specs: Optional[List[BlockSpec]] = None) -> str:
    """Render the doc at ``path`` (default: the canonical location)."""
    path = path or doc_path()
    return render_doc(path.read_text(encoding="utf-8"), specs)


def refresh_file(path: Optional[Path] = None, specs: Optional[List[BlockSpec]] = None) -> bool:
    """Render and write the doc in place. Returns True if it changed."""
    path = path or doc_path()
    original = path.read_text(encoding="utf-8")
    rendered = render_doc(original, specs)
    if rendered != original:
        path.write_text(rendered, encoding="utf-8")
        return True
    return False
