"""Produce prompt-ready slices of the self-knowledge document.

Two flavors are supported (see :mod:`donald.prompt`):

- **slim**: identity + core principles + a bare capability name list.
  Small enough (~500 tokens) to inject on every turn.
- **full**: the entire freshly-rendered document, for turns where the
  agent must reason about whether a capability exists.
"""

from __future__ import annotations

import re
from typing import Optional

from ..tools import ToolRegistry

_SECTION_RE_TMPL = r"^##\s+{heading}\s*$(?P<body>.*?)(?=^##\s+|\Z)"


def extract_section(doc_text: str, heading: str) -> str:
    """Return the markdown body under ``## heading`` (excludes the heading)."""
    pattern = re.compile(
        _SECTION_RE_TMPL.format(heading=re.escape(heading)),
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(doc_text)
    return m.group("body").strip() if m else ""


def slim_summary(registry: ToolRegistry, doc_text: str) -> str:
    """Build the ~500-token slim self-knowledge block."""
    parts = []
    identity = extract_section(doc_text, "Identity")
    if identity:
        parts.append("## Who you are\n" + identity)
    principles = extract_section(doc_text, "Core principles")
    if principles:
        parts.append("## Principles\n" + principles)
    names = ", ".join(registry.names())
    parts.append(
        "## Capabilities\nTools you can call: "
        + (names if names else "_none_")
        + ".\nNever claim a tool that is not in this list."
    )
    return "\n\n".join(parts)
