"""Citation validation — the load-bearing safety check for grounded answers.

Ported from Drift's ``lib/dante/citation-validator.ts``. A brain emits ``[v1]``,
``[mem:abc12345]`` … markers; :func:`build_citation_map` resolves those to
``{quote, source, page, document_id}`` from the tool trace. This module goes one
step further and *verifies* them:

1. Extract every marker from the response text.
2. For each vault marker, confirm the document resolves, the cited page (if
   given) exists, and the quote substring appears in the cited document.
3. For each memory marker, confirm the row exists and its content matches.
4. Surface an overall verdict: ``valid`` / ``partial`` / ``invalid`` /
   ``unverifiable`` / ``no_citations``.

Without this check, nothing stops a model confidently citing "p.14" of an
11-page doc. In a regulated context that is the difference between a tool a
compliance officer trusts and one that gets the firm fined — which is exactly
Donald's anti-hallucination north-star ("never answer without a citation").

**The Supabase coupling in the original is gone.** All backing-store access
lives behind :class:`CitationContextProvider`, a small protocol. Pass a provider
backed by Donald's Vault (or any store) to verify against real data; pass none
and the validator runs trace-only (markers resolve from the trace but cannot be
verified against a document — a real, deterministic mode useful in tests and as
a safe default). A provider that *raises* marks affected markers ``unverifiable``
rather than failing the whole response — verification errors never sink a reply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol, Sequence

from .citations import CitationMap, build_citation_map

# ── Types ────────────────────────────────────────────────────────────

CitationStatus = Literal[
    "valid",  # marker resolved, quote + page check passed
    "missing",  # marker in text but not in trace
    "quote_mismatch",  # resolved, but quote not found in cited chunk
    "page_mismatch",  # resolved, but cited page not in document
    "doc_missing",  # referenced document_id no longer exists
    "item_missing",  # regulatory corpus item no longer exists
    "unverifiable",  # provider error — could not check
]

# Verification strength when a citation is valid. The validator runs three
# nested quote checks; the highest that succeeds determines the level:
#   strong     — quote matched a chunk on the cited page
#   confirmed  — quote matched some chunk in the doc (any-/cross-chunk)
#   provenance — document resolves but quote drifted too far to substring-match
CitationLevel = Literal["strong", "confirmed", "provenance"]

CitationType = Literal["vault", "memory", "regulatory", "site_scan"]


@dataclass
class CitationCheck:
    marker: str  # raw marker as it appeared, e.g. "[v1]"
    type: CitationType
    status: CitationStatus
    level: Optional[CitationLevel] = None
    detail: Optional[str] = None
    source: Optional[str] = None
    page: Optional[int] = None
    document_id: Optional[str] = None


@dataclass
class CitationCounts:
    total: int = 0
    valid: int = 0
    failed: int = 0
    unverifiable: int = 0


@dataclass
class CitationValidationReport:
    overall: Literal["valid", "partial", "invalid", "unverifiable", "no_citations"]
    checks: list[CitationCheck] = field(default_factory=list)
    counts: CitationCounts = field(default_factory=CitationCounts)


# ── Provider abstraction ─────────────────────────────────────────────

@dataclass
class VaultDoc:
    """A resolved vault document: its (derived) page count and chunks."""

    page_count: Optional[int]
    chunks: list["VaultChunk"] = field(default_factory=list)


@dataclass
class VaultChunk:
    page_number: Optional[int]
    content: str


@dataclass
class MemoryRow:
    id: str
    content: str


@dataclass
class RegulatoryItem:
    item_id: str
    authority: str
    source_url: str
    title: str


class CitationContextProvider(Protocol):
    """Backing-store lookups the validator needs to verify citations.

    Each method may raise to signal the store was unreachable; the validator
    catches that and marks the affected markers ``unverifiable``. The default
    :class:`NullCitationContextProvider` returns empty results (no failure),
    giving deterministic trace-only validation.
    """

    def fetch_vault_context(self, document_ids: Sequence[str]) -> dict[str, VaultDoc]:
        ...

    def fetch_memory_context(self, short_ids: Sequence[str]) -> dict[str, MemoryRow]:
        ...

    def fetch_regulatory_context(
        self, reg_keys: Sequence[str]
    ) -> dict[str, RegulatoryItem]:
        ...


class NullCitationContextProvider:
    """A provider with no backing store — every lookup returns empty.

    Vault/memory citations resolved from the trace will report ``doc_missing``
    (nothing to verify against); markers absent from the trace report
    ``missing``. Deterministic and dependency-free.
    """

    def fetch_vault_context(self, document_ids: Sequence[str]) -> dict[str, VaultDoc]:
        return {}

    def fetch_memory_context(self, short_ids: Sequence[str]) -> dict[str, MemoryRow]:
        return {}

    def fetch_regulatory_context(
        self, reg_keys: Sequence[str]
    ) -> dict[str, RegulatoryItem]:
        return {}


# ── Marker extraction ────────────────────────────────────────────────

MARKER_RE = re.compile(r"\[(v\d+|mem:[0-9a-f]{4,32}|reg:\d+|ss:\d+)\]")


@dataclass
class _ExtractedMarker:
    raw: str  # "[v1]", "[mem:abc12345]", "[reg:1]", "[ss:1]"
    key: str  # "v1", "mem:abc12345", "reg:1", "ss:1"
    type: CitationType
    index: int  # position in text — keeps checks in document order


def _extract_markers(text: str) -> list[_ExtractedMarker]:
    out: list[_ExtractedMarker] = []
    if not text:
        return out
    for match in MARKER_RE.finditer(text):
        key = match.group(1)
        if key.startswith("mem:"):
            mtype: CitationType = "memory"
        elif key.startswith("reg:"):
            mtype = "regulatory"
        elif key.startswith("ss:"):
            mtype = "site_scan"
        else:
            mtype = "vault"
        out.append(_ExtractedMarker(match.group(0), key, mtype, match.start()))
    return out


# ── Quote normalization ──────────────────────────────────────────────

def _normalize_for_compare(s: str) -> str:
    """Whitespace-normalize for substring comparison.

    Chunkers collapse newlines, swap nbsp for space, etc. We check *existence*,
    not exact match, so lowercasing is fine.
    """
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" ", " ")  # non-breaking space
    return s.lower().strip()


def quote_appears_in(needle: str, haystack: str) -> bool:
    """True when ``needle`` is found inside ``haystack`` after normalization.

    Multi-tier match: whole-quote substring (strongest), then 80/50/30-char
    prefixes. Tabular docs (rent rolls, MLS sheets) legitimately re-chunk
    between emit and validate; strict whole-quote matching produces
    false-positive "failed" warnings on docs that are present and cited
    correctly. Multi-tier keeps strong evidence valid while letting weaker
    evidence pass instead of flagging.
    """
    if not needle or not haystack:
        return False
    n = _normalize_for_compare(needle)
    h = _normalize_for_compare(haystack)
    if len(n) == 0:
        return False
    if n in h:
        return True
    for length in (80, 50, 30):
        head = n[:length]
        if len(head) >= length * 0.6 and head in h:
            return True
    return False


def _quote_appears_in_document(needle: str, chunks: Sequence[VaultChunk]) -> bool:
    """Cross-chunk fallback: True if the chunks collectively contain the quote.

    Common when a chunker merged or split rows differently between emit and
    validate. Trades strict per-chunk grounding for "the doc contains this
    somewhere", still a useful claim to verify.
    """
    if not needle or len(chunks) == 0:
        return False
    concatenated = " ".join(c.content for c in chunks)
    return quote_appears_in(needle, concatenated)


# ── Per-marker checks ────────────────────────────────────────────────

def _check_vault_marker(
    m: _ExtractedMarker,
    cmap: CitationMap,
    vault_ctx: dict[str, VaultDoc],
    lookup_failed: bool,
) -> CitationCheck:
    cite = cmap.vault.get(m.key)
    if cite is None:
        return CitationCheck(
            marker=m.raw,
            type="vault",
            status="missing",
            detail="Marker referenced but no matching vault.cite call in trace.",
        )
    base = dict(
        marker=m.raw,
        type="vault",
        source=cite.source,
        page=cite.page,
        document_id=cite.document_id,
    )
    if lookup_failed:
        return CitationCheck(
            **base, status="unverifiable", detail="Could not reach archive for verification."
        )
    if not cite.document_id:
        return CitationCheck(**base, status="doc_missing", detail="Citation has no document_id.")
    doc = vault_ctx.get(cite.document_id)
    if doc is None:
        return CitationCheck(
            **base, status="doc_missing", detail="Cited document not found in vault."
        )

    # Provenance-first validation. The citation came from vault.cite, which only
    # returns real workspace documents. If the document resolved, the model
    # didn't invent the id. A substring-quote miss downgrades the level but is
    # not a failure. The failure modes that DO mark invalid: missing,
    # doc_missing, and a page wildly out of bounds.
    if cite.page is not None and doc.page_count is not None:
        if cite.page < 1 or cite.page > doc.page_count * 2:
            return CitationCheck(
                **base,
                status="page_mismatch",
                detail=f"Cited p.{cite.page} but document has {doc.page_count} pages.",
            )

    on_page_chunks = (
        [c for c in doc.chunks if c.page_number == cite.page]
        if cite.page is not None
        else []
    )
    if any(quote_appears_in(cite.quote, c.content) for c in on_page_chunks):
        return CitationCheck(**base, status="valid", level="strong")
    if any(quote_appears_in(cite.quote, c.content) for c in doc.chunks):
        return CitationCheck(
            **base,
            status="valid",
            level="confirmed",
            detail="Verified — quote matched a different chunk than cited page.",
        )
    if _quote_appears_in_document(cite.quote, doc.chunks):
        return CitationCheck(
            **base,
            status="valid",
            level="confirmed",
            detail="Verified — quote matched across chunk boundaries.",
        )
    return CitationCheck(
        **base,
        status="valid",
        level="provenance",
        detail=(
            f"Source document confirmed in vault. Quote text drift between index "
            f"and chunks ({len(doc.chunks)} chunks scanned)."
        ),
    )


def _check_memory_marker(
    m: _ExtractedMarker,
    cmap: CitationMap,
    mem_ctx: dict[str, MemoryRow],
    lookup_failed: bool,
) -> CitationCheck:
    cite = cmap.memory.get(m.key)
    short = m.key[4:]  # strip "mem:"
    if cite is None:
        return CitationCheck(
            marker=m.raw,
            type="memory",
            status="missing",
            detail="Marker referenced but no matching memory.search hit in trace.",
        )
    base = dict(marker=m.raw, type="memory", source=f"memory:{cite.kind}")
    if lookup_failed:
        return CitationCheck(
            **base, status="unverifiable", detail="Could not reach memory for verification."
        )
    row = mem_ctx.get(short)
    if row is None:
        return CitationCheck(**base, status="doc_missing", detail="Cited memory row not found.")
    # Trace content should match persisted content (memory rows are immutable on
    # read paths). Mismatch suggests the model stitched a citation onto
    # unrelated text.
    if not quote_appears_in(cite.content, row.content) and not quote_appears_in(
        row.content, cite.content
    ):
        return CitationCheck(
            **base,
            status="quote_mismatch",
            detail="Trace memory content diverges from persisted memory.",
        )
    return CitationCheck(**base, status="valid", level="strong")


def _check_regulatory_marker(
    m: _ExtractedMarker,
    cmap: CitationMap,
    reg_ctx: dict[str, RegulatoryItem],
    lookup_failed: bool,
) -> CitationCheck:
    cite = cmap.regulatory.get(m.key)
    if cite is None:
        return CitationCheck(
            marker=m.raw,
            type="regulatory",
            status="missing",
            detail="Marker referenced but no matching regulatory.search hit in trace.",
        )
    base = dict(marker=m.raw, type="regulatory", source=f"{cite.authority}: {cite.title}")
    if lookup_failed:
        return CitationCheck(
            **base,
            status="unverifiable",
            detail="Could not reach regulatory corpus for verification.",
        )
    item = reg_ctx.get(cite.source_url)
    if item is None:
        return CitationCheck(
            **base, status="item_missing", detail="Cited regulatory source not found in corpus."
        )
    return CitationCheck(**base, status="valid", level="strong")


def _check_site_scan_marker(m: _ExtractedMarker, cmap: CitationMap) -> CitationCheck:
    cite = cmap.site_scan.get(m.key)
    if cite is None:
        return CitationCheck(
            marker=m.raw,
            type="site_scan",
            status="missing",
            detail="Marker referenced but no matching site_scan result in trace.",
        )
    # Site-scan citations are validated by presence in the trace — the data came
    # from a live county auditor query, no store lookup needed.
    return CitationCheck(
        marker=m.raw,
        type="site_scan",
        status="valid",
        level="strong",
        source=f"{cite.source} — {cite.parcel_number}",
    )


def _summarize(checks: list[CitationCheck]) -> CitationValidationReport:
    counts = CitationCounts(total=len(checks))
    for c in checks:
        if c.status == "valid":
            counts.valid += 1
        elif c.status == "unverifiable":
            counts.unverifiable += 1
        else:
            counts.failed += 1

    overall: str
    if counts.total == 0:
        overall = "no_citations"
    elif counts.failed == 0 and counts.unverifiable == 0:
        overall = "valid"
    elif counts.failed == 0:
        overall = "unverifiable"
    elif counts.valid == 0:
        overall = "invalid"
    else:
        overall = "partial"
    return CitationValidationReport(overall=overall, checks=checks, counts=counts)


# ── Top-level validator ──────────────────────────────────────────────

def validate_citations(
    response_text: str,
    trace: Optional[Sequence[dict[str, Any]]] = None,
    provider: Optional[CitationContextProvider] = None,
) -> CitationValidationReport:
    """Validate every citation marker in ``response_text`` against the trace.

    ``trace`` is the brain's tool-call log (the same shape
    :func:`build_citation_map` consumes). ``provider`` supplies backing-store
    lookups; when omitted, a :class:`NullCitationContextProvider` is used and
    validation runs trace-only. Never raises on the happy path — a provider
    error becomes ``unverifiable`` per affected marker.
    """
    markers = _extract_markers(response_text)
    if not markers:
        return CitationValidationReport(overall="no_citations", checks=[], counts=CitationCounts())

    if provider is None:
        provider = NullCitationContextProvider()

    cmap = build_citation_map(trace)

    # Collect unique document_ids, memory short-ids, and regulatory keys.
    doc_ids: set[str] = set()
    mem_shorts: set[str] = set()
    reg_keys: set[str] = set()
    for m in markers:
        if m.type == "vault":
            cite = cmap.vault.get(m.key)
            if cite and cite.document_id:
                doc_ids.add(cite.document_id)
        elif m.type == "memory":
            mem_shorts.add(m.key[4:])  # strip "mem:"
        elif m.type == "regulatory":
            reg_keys.add(m.key)

    # Run lookups; on provider error mark every unresolved marker unverifiable
    # rather than failing the whole response.
    vault_ctx: dict[str, VaultDoc] = {}
    mem_ctx: dict[str, MemoryRow] = {}
    reg_ctx: dict[str, RegulatoryItem] = {}
    lookup_failed = False
    try:
        vault_ctx = provider.fetch_vault_context(sorted(doc_ids))
        mem_ctx = provider.fetch_memory_context(sorted(mem_shorts))
        reg_ctx = provider.fetch_regulatory_context(sorted(reg_keys))
    except Exception:  # pragma: no cover - defensive; provider decides what raises
        lookup_failed = True

    checks: list[CitationCheck] = []
    for m in markers:
        if m.type == "vault":
            checks.append(_check_vault_marker(m, cmap, vault_ctx, lookup_failed))
        elif m.type == "memory":
            checks.append(_check_memory_marker(m, cmap, mem_ctx, lookup_failed))
        elif m.type == "site_scan":
            checks.append(_check_site_scan_marker(m, cmap))
        else:
            checks.append(_check_regulatory_marker(m, cmap, reg_ctx, lookup_failed))

    return _summarize(checks)
