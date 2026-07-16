"""Tier 1 — the research subagent.

Given a one-paragraph role description it produces a JSON-validated
:class:`SkillsReport`: what the new agent should be capable of, which
existing tools it needs, and which tools it would want that the host doesn't
have yet.

Reliability tricks:

* **24h cache** on the normalized query — a repeat within the window returns
  instantly with no LLM call.
* **Forced tool call on the last iteration** — on the final loop turn the
  model is forced to call ``emit_skills_report`` via
  ``tool_choice={"type": "tool", ...}`` so the worst case is a slightly
  under-researched report rather than an exhausted budget and a crash.

This is a standalone callable (:func:`run_research`); the Factory uses it but
it is useful on its own as a general research helper.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from agent_factory.config import Config
from agent_factory.llm import LLMClient
from agent_factory.models import ResearchReport, SkillsReport
from agent_factory.repos import ResearchReportRepo
from agent_factory.search import SearchBackend
from agent_factory.tools.registry import tool_result

RESEARCH_SYSTEM = """\
You are a research specialist. Your job: research what an agent that does
{domain} should be capable of, and produce a structured Skills Report.

You have access to web_search. Use it 3-6 times to gather real evidence from
real sources (vendor docs, open-source projects, technical blogs).

You MUST end by calling emit_skills_report with these fields:
- domain: the domain you researched
- competencies: 4-8 concrete capabilities the agent should have
- tools_available: tool names from this catalog the agent can use today:
    {tool_catalog}
- tools_wishlist: tools we DON'T have yet that this agent would need
  (name, purpose, external_dependency)
- design_patterns: 2-5 real patterns you observed
- sources: 5-15 sources with url + title + short excerpt (<400 chars)

Only choose tools_available from the catalog above. Quote excerpts must be
SHORT and clearly attributable.
"""

_EMIT_TOOL_NAME = "emit_skills_report"


class ResearchError(Exception):
    pass


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query or "").strip().lower()


def _emit_tool_def() -> dict:
    schema = SkillsReport.model_json_schema()
    return {
        "name": _EMIT_TOOL_NAME,
        "description": "Emit the final structured Skills Report. Call this exactly once when research is complete.",
        "input_schema": schema,
    }


def _web_search_tool_def() -> dict:
    return {
        "name": "web_search",
        "description": "Search the web. Returns a list of results with url, title, and content snippet.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }


def run_research(
    query: str,
    *,
    llm: LLMClient,
    reports_repo: ResearchReportRepo,
    config: Config,
    search_backend: SearchBackend,
    tool_catalog: Optional[list[str]] = None,
    model: Optional[str] = None,
) -> ResearchReport:
    """Produce (or return cached) a Skills Report for *query*."""
    norm = normalize_query(query)
    cached = reports_repo.get_fresh(norm, ttl_hours=config.research_cache_hours)
    if cached is not None:
        return cached

    catalog = tool_catalog or []
    system = RESEARCH_SYSTEM.format(
        domain=query, tool_catalog=", ".join(catalog) if catalog else "(none provided)"
    )
    tools = [_web_search_tool_def(), _emit_tool_def()]
    messages: list[dict] = [
        {"role": "user", "content": f"Research what an agent for this domain needs: {query}"}
    ]

    report_payload: Optional[dict] = None
    max_iters = config.research_max_iters
    last_model = model or config.research_model

    for i in range(max_iters):
        if i == max_iters - 1:
            tool_choice = {"type": "tool", "name": _EMIT_TOOL_NAME}
        else:
            tool_choice = {"type": "auto"}

        resp = llm.create(
            model=last_model,
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=4096,
        )
        tool_uses = resp.tool_uses()

        if not tool_uses:
            # Model produced text only — nudge it to keep going.
            messages.append({"role": "assistant", "content": resp.content})
            messages.append(
                {
                    "role": "user",
                    "content": "Continue your research with web_search, or call emit_skills_report if done.",
                }
            )
            continue

        messages.append({"role": "assistant", "content": resp.content})
        results: list[dict] = []
        emitted = False
        for tu in tool_uses:
            if tu["name"] == _EMIT_TOOL_NAME:
                report_payload = tu["input"]
                emitted = True
                results.append(tool_result(tu["id"], "Skills report received."))
            elif tu["name"] == "web_search":
                hits = search_backend.search(str(tu["input"].get("query", "")))
                results.append(tool_result(tu["id"], json.dumps(hits)[:4000]))
            else:
                results.append(
                    tool_result(tu["id"], f"unknown tool: {tu['name']}", is_error=True)
                )
        messages.append({"role": "user", "content": results})
        if emitted:
            break

    if report_payload is None:
        raise ResearchError("research loop ended without emitting a Skills Report")

    report = SkillsReport.model_validate(report_payload)
    # Keep tools_available honest: drop anything not in the offered catalog.
    if catalog:
        allowed = set(catalog)
        report.tools_available = [t for t in report.tools_available if t in allowed]
    return reports_repo.save(query=query, normalized=norm, report=report)
