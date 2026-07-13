"""Tier 2 — spec markdown + system-prompt generation.

Turns a :class:`SkillsReport` into:

* a human-readable spec markdown file (``agent-specs/<slug>.md``) for the
  reviewer, including the tool *wishlist* so future-you can see what to build
  next; and
* a generated system prompt for the new agent (one LLM call).

Prompt-injection containment lives here: user-supplied ``role_description``
and ``special_requirements`` are sanitized before they are inlined into the
meta-prompt, and the generated prompt is checked to ensure it paraphrased
rather than copied user input verbatim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agent_factory.config import Config
from agent_factory.llm import LLMClient
from agent_factory.models import SkillsReport
from agent_factory.sanitize import assert_clean, assert_no_verbatim_user_input

PROMPT_WRITER_SYSTEM = """\
You write system prompts for AI sub-agents.

Given:
  - the agent's name
  - the agent's role / domain
  - a Skills Report (competencies, tools, design patterns)
  - any special requirements from the user

Produce a system prompt that:
  - addresses the agent in second person ("You are <name>...")
  - states the agent's domain and competencies clearly
  - tells the agent which tools it has and when to use them
  - encodes any special requirements
  - is 200-500 words

IMPORTANT: paraphrase the user's role description and requirements in your own
words. Never copy long spans of user-supplied text verbatim into the prompt.

Return ONLY the system prompt text. No preamble, no commentary.
"""

_REVISION_TEMPLATE = """\

The previous draft was:
---
{prior_prompt}
---
The user asked for these changes:
{revision_feedback}
Produce a revised system prompt incorporating the feedback.
"""


def generate_system_prompt(
    *,
    llm: LLMClient,
    name: str,
    role: str,
    report: SkillsReport,
    special_requirements: Optional[str] = None,
    prior_prompt: Optional[str] = None,
    revision_feedback: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[Config] = None,
) -> str:
    """Generate (or revise) a spawned agent's system prompt."""
    cfg = config or Config.load()
    safe_role = assert_clean(role, field="role_description")
    safe_reqs = assert_clean(special_requirements or "", field="special_requirements")

    user_msg = (
        f"Agent name: {name}\n"
        f"Role / domain: {safe_role}\n"
        f"Special requirements: {safe_reqs or '(none)'}\n\n"
        f"Skills Report (JSON):\n{report.model_dump_json(indent=2)}\n"
    )
    if prior_prompt and revision_feedback:
        # revision feedback is reviewer-supplied; sanitize it too.
        safe_feedback = assert_clean(revision_feedback, field="revision_feedback")
        user_msg += _REVISION_TEMPLATE.format(
            prior_prompt=prior_prompt, revision_feedback=safe_feedback
        )

    resp = llm.create(
        model=model or cfg.prompt_model,
        system=PROMPT_WRITER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=2048,
    )
    prompt = resp.text()

    # Defense in depth: ensure the model paraphrased rather than copied.
    assert_no_verbatim_user_input(prompt, safe_role, safe_reqs)
    return prompt


def write_spec_markdown(
    *,
    slug: str,
    name: str,
    role: str,
    special_requirements: Optional[str],
    report: SkillsReport,
    tool_allowlist: list[str],
    model: str,
    config: Config,
) -> Path:
    """Write the human-readable spec markdown and return its path."""
    safe_role = assert_clean(role, field="role_description")
    safe_reqs = assert_clean(special_requirements or "", field="special_requirements")

    config.specs_dir.mkdir(parents=True, exist_ok=True)
    path = config.specs_dir / f"{slug}.md"

    lines: list[str] = []
    lines.append(f"# Agent spec: {name}")
    lines.append("")
    lines.append(f"- **Slug:** `{slug}`")
    lines.append(f"- **Domain:** {report.domain}")
    lines.append(f"- **Model:** `{model}`")
    lines.append("")
    lines.append("## Role")
    lines.append("")
    lines.append(safe_role)
    lines.append("")
    if safe_reqs:
        lines.append("## Special requirements")
        lines.append("")
        lines.append(safe_reqs)
        lines.append("")
    lines.append("## Competencies")
    lines.append("")
    for c in report.competencies:
        lines.append(f"- {c}")
    lines.append("")
    lines.append("## Granted tools")
    lines.append("")
    if tool_allowlist:
        for t in tool_allowlist:
            lines.append(f"- `{t}`")
    else:
        lines.append("_(none)_")
    lines.append("")
    lines.append("## Tool wishlist (build these next)")
    lines.append("")
    if report.tools_wishlist:
        for w in report.tools_wishlist:
            dep = f" — _depends on: {w.external_dependency}_" if w.external_dependency else ""
            lines.append(f"- **`{w.name}`** — {w.purpose}{dep}")
    else:
        lines.append("_(none)_")
    lines.append("")
    lines.append("## Design patterns observed")
    lines.append("")
    for p in report.design_patterns:
        lines.append(f"- {p}")
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for s in report.sources:
        title = s.title or s.url or "source"
        if s.url:
            lines.append(f"- [{title}]({s.url})")
        else:
            lines.append(f"- {title}")
        if s.excerpt:
            lines.append(f"  > {s.excerpt}")
    lines.append("")

    path.write_text("\n".join(lines))
    return path
