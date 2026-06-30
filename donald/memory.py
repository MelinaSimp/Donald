"""Donald's long-term memory — durable notes that survive between sessions.

Memory is a plain Markdown file in the operator's home directory
(`~/.donald/memory.md`), so it persists no matter which directory Donald is
launched from. At startup the CLI loads it into Donald's system prompt; the
`remember` tool appends to it.

Kept deliberately simple: append-only bullets. Curation (editing or pruning)
is a later concern; for now the operator can review with `/memory` and wipe
with `/forget`.
"""

from __future__ import annotations

import pathlib

MEMORY_DIR = pathlib.Path.home() / ".donald"
MEMORY_PATH = MEMORY_DIR / "memory.md"

_HEADER = "# Donald's memory\n\nDurable facts about the operator and their work.\n"


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


def clear() -> bool:
    """Forget everything. Returns True if there was a memory file to remove."""
    if MEMORY_PATH.exists():
        MEMORY_PATH.unlink()
        return True
    return False


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
