"""Filesystem helpers shared by the self-knowledge tooling."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

DOC_RELATIVE = Path("context") / "self" / "donald.md"
ALLOWLIST_RELATIVE = Path("context") / "self" / ".donald-allowlist.txt"


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk upward from ``start`` (default cwd) until a ``.git`` dir is found.

    Falls back to the package's own repo location so the tooling works
    even when invoked from outside a checkout.
    """
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    # Fallback: src/donald/self_knowledge/paths.py -> repo root is parents[3].
    return Path(__file__).resolve().parents[3]


def doc_path(repo_root: Optional[Path] = None) -> Path:
    root = find_repo_root() if repo_root is None else repo_root
    return root / DOC_RELATIVE


def allowlist_path(repo_root: Optional[Path] = None) -> Path:
    root = find_repo_root() if repo_root is None else repo_root
    return root / ALLOWLIST_RELATIVE
