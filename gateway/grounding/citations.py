"""Citation parsing — resolve inline markers against the tool trace.

Ported from Drift's ``lib/dante/citations.ts``. A grounded brain emits inline
markers in its output:

* ``[v1]``, ``[v2]`` … — vault citations. The matching source row lives in the
  trace under the most recent ``vault.cite`` tool output's ``citations[]``.
* ``[mem:abc12345]`` — memory citations, where the hex chunk is the first 8
  chars of a memory row id. Resolved by scanning ``memory.search`` outputs.
* ``[reg:1]``, ``[reg:2]`` … — regulatory-corpus citations. Resolved by walking
  ``regulatory.search`` outputs in document order.
* ``[ss:1]`` — site-scan / parcel citations from a live county query.

Resolution is done entirely from the trace — no extra fetch. The trace already
carries everything needed because the agent loop persists tool outputs verbatim.
``build_citation_map`` turns a trace into a lookup; ``tokenize`` splits response
text into text runs and citation tokens so a UI can wrap citations in chips.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Sequence

CitationType = Literal["vault", "memory", "regulatory", "site_scan"]


@dataclass
class VaultCitation:
    marker: str  # "[v1]"
    quote: str
    source: str  # document title
    page: Optional[int] = None
    document_id: Optional[str] = None


@dataclass
class MemoryCitation:
    id: str  # full uuid
    short_id: str  # first 8 chars
    kind: str  # "fact" | "summary" | "episode"
    content: str
    source_kind: Optional[str] = None
    source_id: Optional[str] = None


@dataclass
class RegulatoryCitation:
    marker: str  # "[reg:1]"
    index: int  # 1-based position in the brain's hit list
    authority: str  # "SEC" | "IRS" | "DOL" | "HUD" | etc.
    source_kind: str  # "press_release" | "rev_ruling" | etc.
    source_url: str  # canonical link to the primary source
    title: str
    content: str  # the chunk content used for grounding
    published_at: Optional[str] = None


@dataclass
class SiteScanCitation:
    marker: str  # "[ss:1]"
    index: int  # 1-based position in the result set
    parcel_number: str
    address: str
    county: str
    state: str
    source: str  # "Westmoreland County Auditor" etc.
    source_url: str  # link to county parcel record or ArcGIS service
    accessed_at: str


@dataclass
class CitationMap:
    vault: dict[str, VaultCitation] = field(default_factory=dict)
    memory: dict[str, MemoryCitation] = field(default_factory=dict)
    regulatory: dict[str, RegulatoryCitation] = field(default_factory=dict)
    site_scan: dict[str, SiteScanCitation] = field(default_factory=dict)


# One trace entry is the log of a single tool call. Kept as a loose mapping so
# callers can pass plain dicts straight from the orchestrator's event stream.
TraceEntry = dict[str, Any]


def _result_of(entry: TraceEntry) -> Any:
    """Pull ``output.result`` from a trace entry, tolerating shape drift."""
    output = entry.get("output")
    if not isinstance(output, dict):
        return None
    result = output.get("result")
    if not isinstance(result, dict):
        return None
    return result


def build_citation_map(trace: Optional[Sequence[TraceEntry]]) -> CitationMap:
    """Walk the trace and build a citation lookup.

    Later ``vault.cite`` calls win on conflicting markers (chronologically the
    model is using the most recent set), but in practice the model emits
    citations from one tool call per response so collisions are rare.
    """
    out = CitationMap()
    if not isinstance(trace, (list, tuple)):
        return out

    for entry in trace:
        result = _result_of(entry)
        if result is None:
            continue
        step_name = str(entry.get("step_name", ""))

        # vault.cite → {citations: [{marker, quote, source, page, document_id}]}
        vault_citations = result.get("citations")
        if isinstance(vault_citations, list) and "vault_cite" in step_name:
            for c in vault_citations:
                if not isinstance(c, dict) or not c.get("marker"):
                    continue
                # Strip brackets so the key matches what we extract from text.
                key = str(c["marker"]).replace("[", "").replace("]", "")
                out.vault[key] = VaultCitation(
                    marker=str(c["marker"]),
                    quote=str(c.get("quote", "")),
                    source=str(c.get("source", "(untitled)")) or "(untitled)",
                    page=c.get("page"),
                    document_id=c.get("document_id"),
                )

        # memory.search → {hits: [{id, kind, content, source_kind, source_id}]}
        mem_hits = result.get("hits")
        if isinstance(mem_hits, list) and "memory_search" in step_name:
            for h in mem_hits:
                if not isinstance(h, dict) or not h.get("id"):
                    continue
                short_id = str(h["id"])[:8]
                out.memory[f"mem:{short_id}"] = MemoryCitation(
                    id=str(h["id"]),
                    short_id=short_id,
                    kind=str(h.get("kind", "fact")) or "fact",
                    content=str(h.get("content", "")),
                    source_kind=h.get("source_kind"),
                    source_id=h.get("source_id"),
                )

        # regulatory.search → {hits: [...]}. The formatter assigns [reg:N] in
        # 1-based document order; we reproduce that ordering here so "reg:1"
        # resolves to the first hit, "reg:2" to the second, etc.
        reg_hits = result.get("hits")
        if isinstance(reg_hits, list) and "regulatory_search" in step_name:
            i = 1
            for h in reg_hits:
                if not isinstance(h, dict) or not h.get("source_url"):
                    continue
                key = f"reg:{i}"
                out.regulatory[key] = RegulatoryCitation(
                    marker=f"[{key}]",
                    index=i,
                    authority=str(h.get("authority", "OTHER")) or "OTHER",
                    source_kind=str(h.get("source_kind", "guidance")) or "guidance",
                    source_url=str(h["source_url"]),
                    title=str(h.get("title", "(untitled)")) or "(untitled)",
                    content=str(h.get("content", "")),
                    published_at=h.get("published_at"),
                )
                i += 1

        # site_scan.search / void_analysis → {citations: [{marker, ...}]}
        ss_citations = result.get("citations")
        if isinstance(ss_citations, list) and any(
            tok in step_name
            for tok in ("site_scan", "void_analysis", "survey_area", "survey")
        ):
            for c in ss_citations:
                if not isinstance(c, dict) or not c.get("marker"):
                    continue
                key = str(c["marker"]).replace("[", "").replace("]", "")
                out.site_scan[key] = SiteScanCitation(
                    marker=str(c["marker"]),
                    index=int(c.get("index", 0) or 0),
                    parcel_number=str(c.get("parcel_number", "")),
                    address=str(c.get("address", "")),
                    county=str(c.get("county", "")),
                    state=str(c.get("state", "")),
                    source=str(c.get("source", "")),
                    source_url=str(c.get("source_url", "")),
                    accessed_at=str(c.get("accessed_at", "")),
                )
    return out


# ── Tokenization ─────────────────────────────────────────────────────

@dataclass
class Token:
    """A run of the response: either opaque ``text`` or a ``citation`` marker."""

    kind: Literal["text", "citation"]
    value: str = ""  # populated for text tokens
    raw: str = ""  # populated for citation tokens, e.g. "[v1]"
    key: str = ""  # populated for citation tokens, e.g. "v1"
    type: Optional[CitationType] = None  # populated for citation tokens


CITATION_RE = re.compile(r"\[(v\d+|mem:[0-9a-f]{4,32}|reg:\d+|ss:\d+)\]")


def _type_for_key(key: str) -> CitationType:
    if key.startswith("mem:"):
        return "memory"
    if key.startswith("reg:"):
        return "regulatory"
    if key.startswith("ss:"):
        return "site_scan"
    return "vault"


def tokenize(text: str) -> list[Token]:
    """Split ``text`` into a flat list of text runs and citation tokens.

    Recognized markers: ``[v\\d+]``, ``[mem:<hex>]``, ``[reg:\\d+]``, ``[ss:\\d+]``.
    Everything else is opaque text. An empty string yields a single empty text
    token so renderers always have something to map over.
    """
    if not text:
        return [Token(kind="text", value="")]
    out: list[Token] = []
    last_index = 0
    for match in CITATION_RE.finditer(text):
        start = match.start()
        if start > last_index:
            out.append(Token(kind="text", value=text[last_index:start]))
        key = match.group(1)
        out.append(
            Token(kind="citation", raw=match.group(0), key=key, type=_type_for_key(key))
        )
        last_index = match.end()
    if last_index < len(text):
        out.append(Token(kind="text", value=text[last_index:]))
    return out
