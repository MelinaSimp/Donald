"""Per-response grounding score.

Ported from Drift's ``lib/dante/grounding.ts``. Answers a single trust question:
*is this answer grounded in retrieved sources, or is it general knowledge?*
Computed from the tool trace + the response text:

* ``citation_density`` — cite markers per ~100 words. High density = the model
  is grounding most claims, not a few.
* ``tool_grounding`` — fraction of tool calls that are *retrieval* (memory /
  archive / vault / regulatory / site-scan search) vs. mutating or null. A
  response that only retrieved is grounded; one that didn't retrieve at all is
  general knowledge.
* ``validator_pass_rate`` — fraction of citations that passed the validator. Bad
  citations don't count as grounding.

Combined into a single 0..1 score with a human-readable tier and summary,
suitable for surfacing on the gateway's ``final`` event so the UI can show
"strongly grounded" vs "not verified against workspace documents".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Optional, Sequence

from .citation_validator import CitationValidationReport

RETRIEVAL_TOOLS = frozenset(
    {
        "memory.search",
        "memory_search",
        "archive.search",
        "archive_search",
        "vault.cite",
        "vault_cite",
        "clients.query",
        "clients_query",
        "skill.run",
        "skill_run",
        "regulatory.search",
        "regulatory_search",
        "site_scan.search",
        "site_scan_search",
        "site_scan.detail",
        "site_scan_detail",
        "site_scan.void_analysis",
        "site_scan_void_analysis",
    }
)

_CITATION_RE = re.compile(r"\[(?:v\d+|mem:[0-9a-f]{4,32}|reg:\d+|ss:\d+)\]")

GroundingTier = Literal["strong", "partial", "none"]


@dataclass
class GroundingParts:
    citation_count: int
    word_count: int
    citation_density: float
    retrieval_tools_called: int
    total_tools_called: int
    tool_grounding: float
    validator_pass_rate: float


@dataclass
class GroundingScore:
    score: float  # 0..1 composite
    tier: GroundingTier  # human-readable bucket
    summary: str  # friendly one-liner for the UI
    parts: GroundingParts  # component breakdown for telemetry


def _tool_name(step_name: str) -> str:
    """Step names look like ``agent → memory_search`` — trim the prefix."""
    if "→" in step_name:
        piece = step_name.split("→")[1] if len(step_name.split("→")) > 1 else ""
        return piece.strip()
    return step_name.strip()


def compute_grounding_score(
    response_text: str,
    trace: Optional[Sequence[dict[str, Any]]] = None,
    citation_report: Optional[CitationValidationReport] = None,
) -> GroundingScore:
    text = response_text or ""
    trace = list(trace or [])
    word_count = len([w for w in re.split(r"\s+", text) if len(w) > 0])
    citation_count = len(_CITATION_RE.findall(text))

    # Density per 100 words, normalized to 0..1 with diminishing returns. Three
    # citations per 100 words ≈ saturation; more doesn't keep raising the score.
    raw_density = (citation_count * 100) / word_count if word_count > 0 else 0
    citation_density = min(1.0, raw_density / 3)

    # Tool grounding: of the tool calls in the trace, how many were retrieval?
    retrieval_tools_called = 0
    total_tools_called = 0
    for entry in trace:
        tool = _tool_name(str(entry.get("step_name", "")))
        if not tool:
            continue
        total_tools_called += 1
        if tool in RETRIEVAL_TOOLS:
            retrieval_tools_called += 1
    tool_grounding = (
        retrieval_tools_called / total_tools_called if total_tools_called > 0 else 0
    )

    # Validator pass rate. Default 1 — we don't punish responses that
    # legitimately don't need citations. But if retrieval tools WERE called and
    # zero citations emitted, that's a "searched but didn't cite" gap — score 0.
    validator_pass_rate: float = 1.0
    if citation_report is not None and citation_report.counts.total > 0:
        validator_pass_rate = (
            citation_report.counts.valid / citation_report.counts.total
        )
    elif retrieval_tools_called > 0 and citation_count == 0:
        validator_pass_rate = 0.0

    # Composite weights: citations ARE cited (0.4), the model retrieved (0.3),
    # the citations were real (0.3). A no-retrieval, no-citation response scores
    # 0 — it's general knowledge, which is the right verdict.
    composite = (
        citation_density * 0.4 + tool_grounding * 0.3 + validator_pass_rate * 0.3
    )
    score = (
        0.0
        if retrieval_tools_called == 0 and citation_count == 0
        else min(1.0, composite)
    )

    # Tier mapping. "strong" requires citations and validation; "partial"
    # tolerates one weakness; "none" = no retrieval and no citations at all.
    if score >= 0.7:
        tier: GroundingTier = "strong"
    elif score >= 0.4:
        tier = "partial"
    elif retrieval_tools_called > 0 or citation_count > 0:
        tier = "partial"
    else:
        tier = "none"

    # Friendly summary, built from the validator's per-type valid counts.
    def _valid_of(ctype: str) -> int:
        if citation_report is None:
            return 0
        return sum(
            1 for c in citation_report.checks if c.type == ctype and c.status == "valid"
        )

    vault_count = _valid_of("vault")
    memory_count = _valid_of("memory")
    regulatory_count = _valid_of("regulatory")
    site_scan_count = _valid_of("site_scan")

    if tier == "strong":
        parts_desc: list[str] = []
        if vault_count > 0:
            parts_desc.append(f"{vault_count} vault citation{'' if vault_count == 1 else 's'}")
        if memory_count > 0:
            parts_desc.append(f"{memory_count} memory hit{'' if memory_count == 1 else 's'}")
        if regulatory_count > 0:
            parts_desc.append(
                f"{regulatory_count} regulatory source{'' if regulatory_count == 1 else 's'}"
            )
        if site_scan_count > 0:
            parts_desc.append(
                f"{site_scan_count} parcel record{'' if site_scan_count == 1 else 's'}"
            )
        summary = f"Strongly grounded — {' + '.join(parts_desc) or 'citations verified'}."
    elif tier == "partial":
        summary = "Partially grounded — some claims uncited or unverified."
    else:
        summary = "Not verified against workspace documents."

    return GroundingScore(
        score=round(score * 100) / 100,
        tier=tier,
        summary=summary,
        parts=GroundingParts(
            citation_count=citation_count,
            word_count=word_count,
            citation_density=round(citation_density * 100) / 100,
            retrieval_tools_called=retrieval_tools_called,
            total_tools_called=total_tools_called,
            tool_grounding=round(tool_grounding * 100) / 100,
            validator_pass_rate=round(validator_pass_rate * 100) / 100,
        ),
    )
