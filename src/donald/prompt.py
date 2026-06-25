"""Assembly of the system prompt handed to the LLM on each turn.

:func:`build_system_prompt` is the single place where the final prompt
string is produced. It injects Donald's self-knowledge so the agent's
claims about itself stay grounded in the code.

Flavors (controlled by the ``self_knowledge`` argument, defaulting to the
``DONALD_SELF_KNOWLEDGE`` env var, then ``slim``):

- ``slim``  — identity + principles + capability names (~500 tokens),
  injected on every turn. The recommended default.
- ``full``  — the entire freshly-rendered self-knowledge doc, for turns
  where the agent must reason about whether a capability exists.
- ``none``  — no self-knowledge block (just preamble + tool list).
"""

from __future__ import annotations

import os
from typing import Optional

from .tools import ToolRegistry, build_default_registry

SYSTEM_PREAMBLE = (
    "You are Donald, a tool-using conversational AI assistant. "
    "You are helpful, concise, and honest about what you can and cannot do."
)

ENV_FLAVOR = "DONALD_SELF_KNOWLEDGE"


class SelfKnowledgeFlavor:
    NONE = "none"
    SLIM = "slim"
    FULL = "full"


def _resolve_flavor(flavor: Optional[str]) -> str:
    if flavor is not None:
        return flavor
    return os.environ.get(ENV_FLAVOR, SelfKnowledgeFlavor.SLIM)


def _self_knowledge_block(
    flavor: str, registry: ToolRegistry, doc_text: Optional[str]
) -> str:
    if flavor == SelfKnowledgeFlavor.NONE:
        return ""

    # Load the doc lazily and defensively: a missing/broken doc must not
    # break prompt assembly. Imports are deferred to keep `none` cheap.
    if doc_text is None:
        try:
            from .self_knowledge.paths import doc_path

            doc_text = doc_path().read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            doc_text = ""

    if flavor == SelfKnowledgeFlavor.SLIM:
        from .self_knowledge.summary import slim_summary

        return slim_summary(registry, doc_text)

    if flavor == SelfKnowledgeFlavor.FULL:
        if not doc_text:
            return ""
        try:
            from .self_knowledge.render import render_doc

            return render_doc(doc_text)
        except Exception:  # noqa: BLE001
            return doc_text

    raise ValueError(f"unknown self-knowledge flavor: {flavor!r}")


def build_system_prompt(
    registry: Optional[ToolRegistry] = None,
    self_knowledge: Optional[str] = None,
    doc_text: Optional[str] = None,
) -> str:
    """Return the full system prompt for a turn.

    Args:
        registry: Tool registry to describe. Defaults to the runtime
            registry from :func:`build_default_registry`.
        self_knowledge: One of ``slim`` / ``full`` / ``none``. Defaults
            to the ``DONALD_SELF_KNOWLEDGE`` env var, then ``slim``.
        doc_text: Override the doc source (mainly for tests).
    """
    registry = registry if registry is not None else build_default_registry()
    flavor = _resolve_flavor(self_knowledge)

    lines = [SYSTEM_PREAMBLE, "", "Available tools:"]
    for tool in registry.tools():
        lines.append(f"- {tool.name}: {tool.description}")
    prompt = "\n".join(lines)

    block = _self_knowledge_block(flavor, registry, doc_text)
    if block:
        prompt += "\n\n# Self-knowledge\n\n" + block
    return prompt
