from __future__ import annotations

from agent_factory.research import normalize_query, run_research


def test_research_emits_and_persists(config, repos, llm, search):
    report = run_research(
        "document summarization",
        llm=llm,
        reports_repo=repos["reports"],
        config=config,
        search_backend=search,
        tool_catalog=["web_search", "calculator"],
    )
    assert report.report.domain == "document summarization"
    assert len(report.report.competencies) >= 1
    assert len(report.report.sources) >= 2
    # web_search was actually exercised
    assert search.queries
    # persisted
    assert repos["reports"].get(report.id) is not None


def test_research_cache_hit_avoids_llm(config, repos, llm, search):
    run_research(
        "PDF text extraction",
        llm=llm,
        reports_repo=repos["reports"],
        config=config,
        search_backend=search,
        tool_catalog=["web_search"],
    )
    calls_before = len(llm.calls)
    # Same normalized query within 24h -> cache hit, no new LLM calls.
    run_research(
        "  pdf   TEXT extraction ",
        llm=llm,
        reports_repo=repos["reports"],
        config=config,
        search_backend=search,
        tool_catalog=["web_search"],
    )
    assert len(llm.calls) == calls_before


def test_research_drops_uncataloged_tools(config, repos, llm, search):
    # tools_available in the sample includes 'calculator'; restrict catalog.
    report = run_research(
        "document summarization",
        llm=llm,
        reports_repo=repos["reports"],
        config=config,
        search_backend=search,
        tool_catalog=["web_search"],  # calculator NOT offered
    )
    assert "calculator" not in report.report.tools_available


def test_normalize_query():
    assert normalize_query("  Foo   Bar ") == "foo bar"
