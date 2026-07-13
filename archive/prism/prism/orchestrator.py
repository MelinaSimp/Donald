"""Minimal dispatch harness — the entry point other agents call.

A real multi-agent codebase already has an orchestrator; this is a thin stand-in
so Prism is runnable end to end. ``dispatch_design_task``:
  1. resolves/bootstraps the project's design system (concrete, not TODO-shaped),
  2. ensures the preview scaffold exists,
  3. runs the planning loop, which composes the screen via Claude Code.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import agent, bootstrap, config, docs, scaffold
from . import design_tokens as dt


@dataclass
class DispatchOutcome:
    slug: str
    bootstrapped: bool
    scaffolded: bool
    result: agent.DispatchResult


def ensure_project(slug: str, *, register_path: str | None = None) -> bool:
    """Make sure the project resolves and has concrete design.md + brief.md.

    Returns True if anything was bootstrapped this call.
    """
    if register_path is not None:
        docs.register_project(slug, register_path)
    boot = bootstrap.bootstrap_project(slug)
    return boot.created_design or boot.created_brief


def ensure_scaffold(slug: str) -> bool:
    """Ensure the preview app exists. Returns True if it was created this call."""
    design_md = docs.read_project_file(slug, "design.md")
    tokens = dt.parse_tokens(design_md)
    root = docs.resolve_project_root(slug)
    res = scaffold.prepare_scaffold(root, tokens, slug)
    return not res.skipped


def dispatch_design_task(
    slug: str,
    task: str,
    *,
    register_path: str | None = None,
    settings: config.Settings | None = None,
    on_event=None,
    _client=None,
) -> DispatchOutcome:
    """Bootstrap (if needed) and run a design task end to end."""
    bootstrapped = ensure_project(slug, register_path=register_path)
    scaffolded = ensure_scaffold(slug)
    result = agent.run_design_task(
        slug, task, settings=settings, on_event=on_event, _client=_client
    )
    return DispatchOutcome(
        slug=slug,
        bootstrapped=bootstrapped,
        scaffolded=scaffolded,
        result=result,
    )
