"""Citation grounding — Donald's anti-hallucination guardrail.

Ported from Drift's ``lib/dante`` citation subsystem into the gateway. This is
the backbone of the north-star rule "never answer without a citation": a brain
emits inline markers, the trace carries the sources, and this package parses,
*verifies*, and scores how grounded a response is.

Pieces:

* :mod:`source_tiers` — reliability tiers + prompt guidance for sources.
* :mod:`citations` — parse markers and resolve them from the tool trace.
* :mod:`citation_validator` — verify each marker against a backing store (via a
  pluggable :class:`CitationContextProvider`); trace-only by default.
* :mod:`grounding` — a single 0..1 grounding score + tier + summary per response.

The gateway attaches :func:`grounding_for_turn`'s output to each ``final`` event
so the UI can show "strongly grounded" vs "not verified".
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional, Sequence

from .citation_validator import (
    CitationCheck,
    CitationContextProvider,
    CitationValidationReport,
    MemoryRow,
    NullCitationContextProvider,
    RegulatoryItem,
    VaultChunk,
    VaultDoc,
    quote_appears_in,
    validate_citations,
)
from .citations import (
    CitationMap,
    MemoryCitation,
    RegulatoryCitation,
    SiteScanCitation,
    Token,
    VaultCitation,
    build_citation_map,
    tokenize,
)
from .grounding import (
    RETRIEVAL_TOOLS,
    GroundingParts,
    GroundingScore,
    GroundingTier,
    compute_grounding_score,
)
from .source_tiers import TAGS, SourceTag, SourceTier, format_tier_guidance

__all__ = [
    # source tiers
    "SourceTag",
    "SourceTier",
    "TAGS",
    "format_tier_guidance",
    # citations
    "CitationMap",
    "VaultCitation",
    "MemoryCitation",
    "RegulatoryCitation",
    "SiteScanCitation",
    "Token",
    "build_citation_map",
    "tokenize",
    # validator
    "CitationCheck",
    "CitationValidationReport",
    "CitationContextProvider",
    "NullCitationContextProvider",
    "VaultDoc",
    "VaultChunk",
    "MemoryRow",
    "RegulatoryItem",
    "validate_citations",
    "quote_appears_in",
    # grounding
    "GroundingScore",
    "GroundingParts",
    "GroundingTier",
    "RETRIEVAL_TOOLS",
    "compute_grounding_score",
    # convenience
    "grounding_for_turn",
]


def grounding_for_turn(
    response_text: str,
    trace: Optional[Sequence[dict[str, Any]]] = None,
    provider: Optional[CitationContextProvider] = None,
) -> dict[str, Any]:
    """Validate + score one turn and return a plain JSON-serializable dict.

    Convenience wrapper for the gateway: runs :func:`validate_citations` then
    :func:`compute_grounding_score`, and flattens both into a dict ready to
    attach to a streamed event. Fully self-contained — with no ``provider`` it
    runs trace-only and never touches a backing store.
    """
    report = validate_citations(response_text, trace, provider)
    score = compute_grounding_score(response_text, trace, report)
    return {
        "score": score.score,
        "tier": score.tier,
        "summary": score.summary,
        "parts": asdict(score.parts),
        "citations": {
            "overall": report.overall,
            "counts": asdict(report.counts),
            "checks": [asdict(c) for c in report.checks],
        },
    }
