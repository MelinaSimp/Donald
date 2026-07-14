"""Tests for the citation-grounding guardrail (``gateway/grounding``).

Ported from Drift's ``lib/dante`` vitest suites (grounding.test.ts,
citations.test.ts, citation-validator.test.ts) and adapted to the Python port's
deterministic, provider-based validation. Trace-only validation (no provider)
reports ``missing`` for unresolved markers rather than the DB-dependent
``unverifiable`` the original hit against a live Supabase.
"""

from __future__ import annotations

from gateway.grounding import (
    MemoryRow,
    Vault,
    VaultChunk,
    VaultCitationContextProvider,
    VaultDoc,
    build_citation_map,
    chunk_text_with_pages,
    compute_grounding_score,
    format_tier_guidance,
    grounding_for_turn,
    tokenize,
    validate_citations,
)


# ── helpers ──────────────────────────────────────────────────────────

def trace_entry(step_name, output=None, status="complete", step_id="s1"):
    return {"step_id": step_id, "step_name": step_name, "status": status, "output": output}


class _FakeProvider:
    """In-memory provider for exercising the verified (non-trace-only) path."""

    def __init__(self, vault=None, memory=None, regulatory=None):
        self._vault = vault or {}
        self._memory = memory or {}
        self._regulatory = regulatory or {}

    def fetch_vault_context(self, document_ids):
        return {k: v for k, v in self._vault.items() if k in set(document_ids)}

    def fetch_memory_context(self, short_ids):
        return {k: v for k, v in self._memory.items() if k in set(short_ids)}

    def fetch_regulatory_context(self, reg_keys):
        return dict(self._regulatory)


class _ExplodingProvider:
    def fetch_vault_context(self, document_ids):
        raise RuntimeError("store down")

    def fetch_memory_context(self, short_ids):
        raise RuntimeError("store down")

    def fetch_regulatory_context(self, reg_keys):
        raise RuntimeError("store down")


# ── tokenize ─────────────────────────────────────────────────────────

def test_tokenize_empty_string():
    assert tokenize("") == [tokenize("")[0]]
    tokens = tokenize("")
    assert len(tokens) == 1
    assert tokens[0].kind == "text"
    assert tokens[0].value == ""


def test_tokenize_plain_text():
    tokens = tokenize("Hello world, no citations here.")
    assert len(tokens) == 1
    assert tokens[0].kind == "text"
    assert tokens[0].value == "Hello world, no citations here."


def test_tokenize_single_vault_marker():
    tokens = tokenize("Before [v1] after")
    assert len(tokens) == 3
    assert (tokens[0].kind, tokens[0].value) == ("text", "Before ")
    assert tokens[1].kind == "citation"
    assert tokens[1].raw == "[v1]"
    assert tokens[1].key == "v1"
    assert tokens[1].type == "vault"
    assert (tokens[2].kind, tokens[2].value) == ("text", " after")


def test_tokenize_multiple_markers():
    tokens = tokenize("Start [v1] middle [v2] end")
    citations = [t for t in tokens if t.kind == "citation"]
    texts = [t for t in tokens if t.kind == "text"]
    assert [c.key for c in citations] == ["v1", "v2"]
    assert [t.value for t in texts] == ["Start ", " middle ", " end"]


def test_tokenize_marker_types():
    assert tokenize("Recall [mem:abcd1234] detail")[1].type == "memory"
    assert tokenize("Per SEC [reg:42] guidance")[1].type == "regulatory"
    assert tokenize("The parcel [ss:3] is zoned")[1].type == "site_scan"


def test_tokenize_adjacent_markers():
    tokens = tokenize("[v1][v2][mem:12345678]")
    assert len(tokens) == 3
    assert all(t.kind == "citation" for t in tokens)
    assert [t.key for t in tokens] == ["v1", "v2", "mem:12345678"]


def test_tokenize_marker_at_start_and_end():
    start = tokenize("[v1] starts here")
    assert start[0].kind == "citation"
    assert start[1].value == " starts here"
    end = tokenize("ends here [reg:5]")
    assert len(end) == 2
    assert end[0].value == "ends here "
    assert end[1].key == "reg:5"


# ── build_citation_map ───────────────────────────────────────────────

def test_build_citation_map_vault():
    trace = [
        trace_entry(
            "agent → vault_cite",
            {
                "result": {
                    "citations": [
                        {"marker": "[v1]", "quote": "cash capped at 5%", "source": "IPS", "page": 3, "document_id": "doc-1"}
                    ]
                }
            },
        )
    ]
    cmap = build_citation_map(trace)
    assert "v1" in cmap.vault
    assert cmap.vault["v1"].source == "IPS"
    assert cmap.vault["v1"].page == 3
    assert cmap.vault["v1"].document_id == "doc-1"


def test_build_citation_map_memory_and_regulatory_ordering():
    trace = [
        trace_entry(
            "agent → memory_search",
            {"result": {"hits": [{"id": "abcd1234-0000-0000", "kind": "fact", "content": "prefers bonds"}]}},
        ),
        trace_entry(
            "agent → regulatory_search",
            {
                "result": {
                    "hits": [
                        {"source_url": "https://sec.gov/a", "authority": "SEC", "title": "Rule A", "content": "..."},
                        {"source_url": "https://irs.gov/b", "authority": "IRS", "title": "Rul B", "content": "..."},
                    ]
                }
            },
        ),
    ]
    cmap = build_citation_map(trace)
    assert cmap.memory["mem:abcd1234"].content == "prefers bonds"
    assert cmap.regulatory["reg:1"].authority == "SEC"
    assert cmap.regulatory["reg:2"].authority == "IRS"


def test_build_citation_map_ignores_non_dict_trace():
    assert build_citation_map(None).vault == {}
    assert build_citation_map([]).memory == {}


# ── validate_citations (trace-only) ──────────────────────────────────

def test_validate_no_citations():
    r = validate_citations("Hi, no citations here. Just plain text.", [])
    assert r.overall == "no_citations"
    assert r.checks == []
    assert r.counts.total == 0


def test_validate_empty_and_whitespace():
    assert validate_citations("", []).overall == "no_citations"
    assert validate_citations("   \n\t  ", []).counts.total == 0


def test_validate_vault_marker_missing_when_trace_empty():
    r = validate_citations("The IPS limits cash to 5% [v1].", [])
    assert len(r.checks) == 1
    assert r.checks[0].marker == "[v1]"
    assert r.checks[0].type == "vault"
    assert r.checks[0].status == "missing"


def test_validate_multiple_vault_markers():
    r = validate_citations("The IPS [v1] states cash at 5% [v2] and bonds at 40% [v3].", [])
    assert len(r.checks) == 3
    assert all(c.type == "vault" for c in r.checks)


def test_validate_high_numbered_and_large_markers():
    assert validate_citations("Per page [v142], the allocation is 60%.", []).checks[0].marker == "[v142]"
    assert validate_citations("See [v99999] for details.", []).checks[0].marker == "[v99999]"


def test_validate_memory_markers_varying_hex():
    r = validate_citations(
        "Short [mem:abcd] and long [mem:abcdef1234567890abcdef1234567890].", []
    )
    assert len(r.checks) == 2
    assert all(c.type == "memory" for c in r.checks)


def test_validate_all_three_marker_types_and_order():
    r = validate_citations("First [reg:1], then [v1], finally [mem:abcd].", [])
    assert [c.type for c in r.checks] == ["regulatory", "vault", "memory"]


def test_validate_ignores_unrecognized_brackets():
    assert validate_citations("Footnote [1] and [Note] are not markers.", []).overall == "no_citations"
    assert validate_citations("See [this](https://example.com) for more.", []).overall == "no_citations"
    assert validate_citations("The allocation is [60] percent equities.", []).overall == "no_citations"


def test_validate_counts_are_accurate():
    r = validate_citations("[v1] [v2] [mem:aaaa] [reg:5]", [])
    assert r.counts.total == 4
    assert r.counts.valid + r.counts.failed + r.counts.unverifiable == 4


def test_validate_adjacent_markers_no_space():
    assert len(validate_citations("Supported by [v1][v2][mem:1234].", []).checks) == 3


def test_validate_extracts_markers_inside_backticks():
    # Extraction is text-level; code-fence awareness is out of scope.
    assert len(validate_citations("Use `[v1]` as a citation marker.", []).checks) == 1


def test_validate_all_missing_is_invalid():
    r = validate_citations("[v999] [v998] [v997]", [])
    assert r.counts.total == 3
    assert r.overall == "invalid"


# ── validate_citations (with a provider) ─────────────────────────────

def _vault_trace(quote="cash capped at 5%", page=3):
    return [
        trace_entry(
            "agent → vault_cite",
            {"result": {"citations": [{"marker": "[v1]", "quote": quote, "source": "IPS", "page": page, "document_id": "doc-1"}]}},
        )
    ]


def test_validate_vault_strong_when_quote_on_cited_page():
    provider = _FakeProvider(
        vault={"doc-1": VaultDoc(page_count=10, chunks=[VaultChunk(page_number=3, content="the IPS says cash capped at 5% annually")])}
    )
    r = validate_citations("Cash is capped [v1].", _vault_trace(), provider)
    assert r.overall == "valid"
    assert r.checks[0].status == "valid"
    assert r.checks[0].level == "strong"


def test_validate_vault_provenance_when_quote_drifts():
    provider = _FakeProvider(
        vault={"doc-1": VaultDoc(page_count=10, chunks=[VaultChunk(page_number=3, content="unrelated text entirely")])}
    )
    r = validate_citations("Cash is capped [v1].", _vault_trace(), provider)
    assert r.checks[0].status == "valid"
    assert r.checks[0].level == "provenance"


def test_validate_vault_page_out_of_bounds():
    provider = _FakeProvider(vault={"doc-1": VaultDoc(page_count=1, chunks=[VaultChunk(page_number=1, content="cash capped at 5%")])})
    r = validate_citations("Cash [v1].", _vault_trace(page=50), provider)
    assert r.checks[0].status == "page_mismatch"


def test_validate_vault_doc_missing_with_null_provider():
    # Trace resolves the cite, but nothing backs the document.
    r = validate_citations("Cash [v1].", _vault_trace())
    assert r.checks[0].status == "doc_missing"


def test_validate_memory_strong_and_mismatch():
    trace = [
        trace_entry(
            "agent → memory_search",
            {"result": {"hits": [{"id": "abcd1234-xxxx", "kind": "fact", "content": "client prefers bond ladders"}]}},
        )
    ]
    ok = _FakeProvider(memory={"abcd1234": MemoryRow(id="abcd1234-xxxx", content="client prefers bond ladders and low fees")})
    r = validate_citations("Noted [mem:abcd1234].", trace, ok)
    assert r.checks[0].status == "valid"
    assert r.checks[0].level == "strong"

    bad = _FakeProvider(memory={"abcd1234": MemoryRow(id="abcd1234-xxxx", content="totally different persisted content here")})
    r2 = validate_citations("Noted [mem:abcd1234].", trace, bad)
    assert r2.checks[0].status == "quote_mismatch"


def test_validate_provider_error_is_unverifiable():
    r = validate_citations("Cash [v1].", _vault_trace(), _ExplodingProvider())
    assert r.checks[0].status == "unverifiable"
    assert r.overall == "unverifiable"


def test_validate_site_scan_valid_from_trace():
    trace = [
        trace_entry(
            "agent → site_scan_search",
            {"result": {"citations": [{"marker": "[ss:1]", "parcel_number": "123-45", "source": "County Auditor"}]}},
        )
    ]
    r = validate_citations("Parcel [ss:1] is zoned.", trace)
    assert r.checks[0].status == "valid"
    assert r.checks[0].level == "strong"


# ── grounding score ──────────────────────────────────────────────────

def test_grounding_none_for_empty():
    r = compute_grounding_score("", [])
    assert r.score == 0
    assert r.tier == "none"


def test_grounding_none_for_plain_text():
    r = compute_grounding_score("Here is some general advice about investing.", [])
    assert r.score == 0
    assert r.tier == "none"


def test_grounding_none_when_only_non_retrieval_tools():
    r = compute_grounding_score("Done. I sent the email.", [trace_entry("agent → email.send", status="success")])
    assert r.tier == "none"
    assert r.score == 0


def test_grounding_strong_with_density_and_retrieval():
    report = validate_citations(
        "Per the IPS [v1], cash allocation is capped at 5%. The advisor noted [mem:abcd1234] the client prefers bond ladders. Regulatory guidance [reg:1] supports this.",
        [],
    )
    # Force a fully-valid report to mirror the reference expectation.
    for c in report.checks:
        c.status = "valid"
    report.counts.valid = report.counts.total
    report.counts.failed = 0
    r = compute_grounding_score(
        "Per the IPS [v1], cash allocation is capped at 5%. The advisor noted [mem:abcd1234] the client prefers bond ladders. Regulatory guidance [reg:1] supports this.",
        [
            trace_entry("agent → memory_search", status="success"),
            trace_entry("agent → vault_cite", status="success"),
            trace_entry("agent → regulatory_search", status="success"),
        ],
        report,
    )
    assert r.tier == "strong"
    assert r.score >= 0.7
    assert r.parts.citation_count == 3
    assert r.parts.retrieval_tools_called == 3


def test_grounding_zero_pass_rate_when_searched_but_no_citations():
    r = compute_grounding_score(
        "I looked into your question and here is what I found about the market.",
        [trace_entry("agent → memory_search", status="success"), trace_entry("agent → archive_search", status="success")],
    )
    assert r.parts.validator_pass_rate == 0
    assert r.parts.retrieval_tools_called == 2
    assert r.parts.citation_count == 0


def test_grounding_mixed_tools():
    r = compute_grounding_score(
        "Based on the docs [v1], I updated the contact.",
        [
            trace_entry("agent → vault_cite", status="success"),
            trace_entry("agent → clients_query", status="success"),
            trace_entry("agent → email.send", status="success"),
        ],
    )
    assert r.parts.retrieval_tools_called == 2
    assert r.parts.total_tools_called == 3
    assert round(r.parts.tool_grounding, 1) == 0.7


def test_grounding_arrow_prefix_and_bare_names():
    r = compute_grounding_score(
        "Test [v1].",
        [trace_entry("agent → memory.search", status="success"), trace_entry("memory_search", status="success")],
    )
    assert r.parts.retrieval_tools_called == 2


def test_grounding_density_capped_and_score_capped():
    r = compute_grounding_score("[v1] [v2] [v3] [v4] [v5] yes", [trace_entry("agent → vault_cite")])
    assert r.parts.citation_density <= 1
    assert r.score <= 1


def test_grounding_counts_failed_tools():
    r = compute_grounding_score(
        "I tried to look it up but couldn't find anything.",
        [trace_entry("agent → vault_cite", status="error"), trace_entry("agent → memory_search", status="error")],
    )
    assert r.parts.retrieval_tools_called == 2
    assert r.parts.total_tools_called == 2


def test_grounding_file_index_not_retrieval():
    r = compute_grounding_score("Found in file index [v1].", [trace_entry("agent → file_index.search")])
    assert r.parts.retrieval_tools_called == 0
    assert r.parts.total_tools_called == 1


def test_grounding_partial_when_retrieved_but_uncited():
    r = compute_grounding_score(
        "I checked the documents and here is some general advice about leasing.",
        [trace_entry("agent → vault_cite", status="success")],
    )
    assert r.tier == "partial"
    assert r.parts.retrieval_tools_called == 1
    assert r.parts.citation_count == 0


def test_grounding_summary_mentions_source_types():
    report = validate_citations("Per [v1] and [mem:1234abcd] and [reg:1].", [])
    for c in report.checks:
        c.status = "valid"
    report.counts.valid = report.counts.total
    report.counts.failed = 0
    r = compute_grounding_score(
        "Per [v1] and [mem:1234abcd] and [reg:1], this is well-supported advice for your situation.",
        [
            trace_entry("vault_cite", status="success"),
            trace_entry("memory_search", status="success"),
            trace_entry("regulatory_search", status="success"),
        ],
        report,
    )
    assert "vault" in r.summary
    assert "memory" in r.summary
    assert "regulatory" in r.summary


# ── source tiers ─────────────────────────────────────────────────────

def test_format_tier_guidance():
    text = format_tier_guidance()
    assert "TIER 1" in text
    assert "TIER 2" in text
    assert "TIER 3" in text
    assert "Census" in text


# ── Vault + VaultCitationContextProvider ─────────────────────────────

def _vault_cite_trace(quote, page, document_id="lease-1"):
    return [
        trace_entry(
            "agent → vault_cite",
            {"result": {"citations": [{"marker": "[v1]", "quote": quote, "source": "Lease", "page": page, "document_id": document_id}]}},
        )
    ]


def test_chunk_text_with_pages_provenance():
    chunks = chunk_text_with_pages(["hello world foo", "second page text"])
    assert len(chunks) == 1  # small input → single chunk on the first page
    assert chunks[0].page_number == 1
    assert chunks[0].line_start == 1
    assert "hello world foo" in chunks[0].content


def test_chunk_text_with_pages_empty():
    assert chunk_text_with_pages([]) == []
    assert chunk_text_with_pages(["", "   "]) == []


def test_vault_ingest_and_get_in_memory():
    v = Vault()
    doc = v.ingest("lease-1", "Lease", ["The base rent is 5% of gross sales, escalating annually."])
    assert v.get("lease-1") is not None
    assert doc.page_count == 1
    assert v.document_ids() == ["lease-1"]
    assert v.get("nope") is None


def test_vault_provider_verifies_quote_strong():
    v = Vault()
    v.ingest("lease-1", "Lease", ["The base rent is 5% of gross sales, escalating annually."])
    provider = VaultCitationContextProvider(v)
    r = validate_citations("Rent is capped [v1].", _vault_cite_trace("base rent is 5% of gross sales", page=1), provider)
    assert r.overall == "valid"
    assert r.checks[0].status == "valid"
    assert r.checks[0].level == "strong"


def test_vault_provider_provenance_when_quote_not_found():
    v = Vault()
    v.ingest("lease-1", "Lease", ["Entirely unrelated content about parking."])
    provider = VaultCitationContextProvider(v)
    r = validate_citations("Rent [v1].", _vault_cite_trace("base rent is 5%", page=1), provider)
    assert r.checks[0].status == "valid"
    assert r.checks[0].level == "provenance"


def test_vault_provider_doc_missing_for_unknown_document():
    provider = VaultCitationContextProvider(Vault())
    r = validate_citations("Rent [v1].", _vault_cite_trace("anything", page=1, document_id="ghost"), provider)
    assert r.checks[0].status == "doc_missing"


def test_vault_provider_page_out_of_bounds():
    v = Vault()
    v.ingest("lease-1", "Lease", ["Single page lease document."])  # page_count == 1
    provider = VaultCitationContextProvider(v)
    r = validate_citations("Rent [v1].", _vault_cite_trace("Single page", page=99), provider)
    assert r.checks[0].status == "page_mismatch"


def test_vault_file_backed_roundtrip(tmp_path):
    root = tmp_path / "vault"
    v1 = Vault(root=root)
    v1.ingest("lease-1", "Lease", ["The base rent is 5% of gross sales."])
    # A fresh Vault over the same directory sees the persisted document.
    v2 = Vault(root=root)
    assert v2.document_ids() == ["lease-1"]
    provider = VaultCitationContextProvider(v2)
    r = validate_citations("Rent [v1].", _vault_cite_trace("base rent is 5%", page=1), provider)
    assert r.checks[0].status == "valid"


def test_grounding_for_turn_with_vault_provider_is_strong():
    v = Vault()
    v.ingest("lease-1", "Lease", ["The base rent is 5% of gross sales, escalating 3% annually."])
    provider = VaultCitationContextProvider(v)
    out = grounding_for_turn(
        "Per the lease [v1], base rent is 5%.",
        [
            trace_entry(
                "agent → vault_cite",
                {"result": {"citations": [{"marker": "[v1]", "quote": "base rent is 5% of gross sales", "source": "Lease", "page": 1, "document_id": "lease-1"}]}},
                status="success",
            )
        ],
        provider,
    )
    assert out["citations"]["overall"] == "valid"
    assert out["tier"] == "strong"


# ── grounding_for_turn (integration convenience) ─────────────────────

def test_grounding_for_turn_is_json_serializable_dict():
    out = grounding_for_turn(
        "General advice, no sources.",
        [trace_entry("agent → hermes_execute", status="success")],
    )
    assert out["tier"] == "none"
    assert out["citations"]["overall"] == "no_citations"
    assert set(out.keys()) == {"score", "tier", "summary", "parts", "citations"}
    # No dataclasses leak through — everything is plain JSON types.
    import json

    json.dumps(out)
