"""Drift checker for the hand-written sections of the self-knowledge doc.

It scans only the hand-written prose (AUTO blocks are skipped, since they
are regenerated) for backtick-quoted references to:

- **file paths**     — verified against the filesystem
- **qualified symbols** (``Class.method``) — verified against an AST
  index of the source tree
- **bare names**     — tools, sub-agents, integrations, env vars, or any
  defined function/class

References listed in the allowlist file are ignored (useful for
future-tense plans or third-party examples). Verification uses static
reads and ``ast`` — never ``grep`` — so it doesn't false-positive on
strings or comments.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

from .parser import SelfKnowledgeDoc
from .paths import allowlist_path, doc_path, find_repo_root

_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_PATH_EXTS = {".py", ".md", ".txt", ".sh", ".toml", ".yml", ".yaml", ".cfg", ".ini", ".json"}
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


@dataclass(frozen=True)
class DriftFinding:
    kind: str  # "file" | "symbol" | "name"
    reference: str
    location_in_doc: int  # 1-based line number
    reason: str


# -- code index ---------------------------------------------------------


@dataclass
class CodeIndex:
    names: Set[str]  # bare function/class/method names
    dotted: Set[str]  # Class.method
    files: Set[str]  # n/a here; paths checked against fs directly


def build_symbol_index(src_root: Path) -> CodeIndex:
    names: Set[str] = set()
    dotted: Set[str] = set()
    for py in sorted(src_root.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.add(item.name)
                        dotted.add(f"{node.name}.{item.name}")
    return CodeIndex(names=names, dotted=dotted, files=set())


def live_names() -> Set[str]:
    """Tool / sub-agent / integration / env-var names from the live sources.

    Best-effort: any source that fails to import simply contributes
    nothing, so the checker degrades rather than crashing.
    """
    names: Set[str] = set()
    try:
        from ..tools import build_default_registry

        names.update(build_default_registry().names())
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..subagents import all_subagents

        names.update(s.name for s in all_subagents())
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..integrations import all_integrations

        for integ in all_integrations():
            names.add(integ.name)
            names.add(integ.env_var)
    except Exception:  # noqa: BLE001
        pass
    return names


# -- allowlist ----------------------------------------------------------


def load_allowlist(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    entries: Set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            entries.add(line)
    return entries


# -- classification + verification --------------------------------------


def _looks_like_path(token: str) -> bool:
    if "/" in token:
        return True
    suffix = Path(token).suffix
    return suffix in _PATH_EXTS


def _verify_path(token: str, repo_root: Path) -> Optional[str]:
    rel = token.rstrip("/")
    target = repo_root / rel
    if token.endswith("/"):
        if not target.is_dir():
            return f"directory not found: {token}"
        return None
    if not target.exists():
        return f"path not found: {token}"
    return None


def _verify_symbol(token: str, index: CodeIndex, names: Set[str]) -> Optional[str]:
    if "." in token:
        if token in index.dotted:
            return None
        # module.function or Class.attr — accept if the final name is defined.
        if token.rsplit(".", 1)[-1] in index.names:
            return None
        return f"qualified symbol not found: {token}"
    if token in index.names or token in names:
        return None
    return f"name not found: {token}"


def extract_references(doc: SelfKnowledgeDoc) -> List[Tuple[str, str, int]]:
    """Return (kind, reference, line) for every backtick token in prose."""
    refs: List[Tuple[str, str, int]] = []
    for span in doc.handwritten_spans():
        for m in _BACKTICK_RE.finditer(span.text):
            token = m.group(1).strip()
            line = span.start_line + span.text[: m.start()].count("\n")
            if _looks_like_path(token):
                refs.append(("file", token, line))
            elif _IDENT_RE.match(token):
                kind = "symbol" if "." in token else "name"
                refs.append((kind, token, line))
            # anything else is ordinary backticked prose; ignore.
    return refs


def check_drift(
    repo_root: Optional[Path] = None,
    doc_text: Optional[str] = None,
) -> List[DriftFinding]:
    root = repo_root or find_repo_root()
    text = doc_text if doc_text is not None else doc_path(root).read_text(encoding="utf-8")
    doc = SelfKnowledgeDoc.parse(text)

    index = build_symbol_index(root / "src")
    names = live_names()
    allow = load_allowlist(allowlist_path(root))

    findings: List[DriftFinding] = []
    for kind, ref, line in extract_references(doc):
        if ref in allow:
            continue
        if kind == "file":
            reason = _verify_path(ref, root)
        else:
            reason = _verify_symbol(ref, index, names)
        if reason:
            findings.append(DriftFinding(kind=kind, reference=ref, location_in_doc=line, reason=reason))
    return findings
