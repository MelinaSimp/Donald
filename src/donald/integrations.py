"""External services Donald talks to.

This module is the canonical registration site for integrations. The
self-knowledge integrations generator imports :func:`all_integrations`
and renders from it, so the docs stay in sync with the code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Integration:
    """A single external service Donald can use."""

    name: str
    purpose: str
    env_var: str
    category: str = "external"

    @property
    def configured(self) -> bool:
        """True when the integration's credential is present in the env."""
        return bool(os.environ.get(self.env_var))


INTEGRATIONS: List[Integration] = [
    Integration("Anthropic", "Primary LLM for reasoning and conversation.", "ANTHROPIC_API_KEY", "llm"),
    Integration("OpenAI", "Fallback LLM and text embeddings.", "OPENAI_API_KEY", "llm"),
    Integration("SMTP", "Outbound email backing the send_email tool.", "SMTP_URL", "communication"),
    Integration("Tavily", "Web search backend for the web_search tool.", "TAVILY_API_KEY", "research"),
]


def all_integrations() -> List[Integration]:
    """Return every configured-or-not integration, in declaration order."""
    return list(INTEGRATIONS)
