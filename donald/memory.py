"""Donald's long-term memory — durable notes that survive between sessions.

Memory is a plain Markdown file in the operator's home directory
(`~/.donald/memory.md`), so it persists no matter which directory Donald is
launched from. At startup the CLI loads it into Donald's system prompt; the
`remember` tool appends to it.

Donald adds facts with `remember` (append) and tidies them with `update_memory`
(rewrite the whole set), so notes don't drift stale or contradict each other.
The operator can review with `/memory` and wipe with `/forget`. A one-level
backup (`memory.bak`) guards against a careless rewrite.
"""

from __future__ import annotations

import pathlib

MEMORY_DIR = pathlib.Path.home() / ".donald"
MEMORY_PATH = MEMORY_DIR / "memory.md"
BACKUP_PATH = MEMORY_DIR / "memory.bak"

# Every header line starts with `#` so `block()` strips the whole header and
# never leaks boilerplate into Donald's remembered facts.
_HEADER = "# Donald's memory\n# Durable facts about the operator and their work.\n"


def load() -> str:
    """Return the raw memory text, or '' if there's nothing remembered yet."""
    if not MEMORY_PATH.is_file():
        return ""
    return MEMORY_PATH.read_text(encoding="utf-8")


def remember(note: str) -> str:
    """Append a single durable fact. Returns a short confirmation."""
    note = note.strip()
    if not note:
        return "Nothing to remember (empty note)."
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_PATH.exists():
        MEMORY_PATH.write_text(_HEADER, encoding="utf-8")
    with MEMORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {note}\n")
    return f"Noted: {note}"


def _strip_headers(text: str) -> str:
    """Drop any Markdown header lines so we don't duplicate ours."""
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    return "\n".join(lines).strip()


def replace(content: str) -> str:
    """Rewrite the whole memory with a curated version. Backs up the old copy."""
    body = _strip_headers(content.strip())
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if MEMORY_PATH.exists():
        MEMORY_PATH.replace(BACKUP_PATH)  # one-level undo for a careless rewrite
    if not body:
        MEMORY_PATH.write_text(_HEADER, encoding="utf-8")
        return "Memory cleared."
    MEMORY_PATH.write_text(f"{_HEADER}\n{body}\n", encoding="utf-8")
    count = sum(1 for ln in body.splitlines() if ln.strip())
    return f"Memory updated ({count} item{'s' if count != 1 else ''})."


def clear() -> bool:
    """Forget everything, backup included. True if there was anything to remove."""
    removed = False
    for path in (MEMORY_PATH, BACKUP_PATH):
        if path.exists():
            path.unlink()
            removed = True
    return removed


def block() -> str:
    """The system-prompt section that surfaces remembered facts to Donald."""
    text = load().strip()
    # Drop the file header — Donald only needs the facts themselves.
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    facts = "\n".join(lines).strip()
    if not facts:
        return ""
    return (
        "\n\nWhat you remember about your operator and their work, from past "
        "sessions (treat as background, not gospel — confirm if it seems stale):\n"
        f"{facts}"
    )
