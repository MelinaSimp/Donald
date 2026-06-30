"""Shared test helpers: a scriptable fake LLM responder."""

from __future__ import annotations

from agent_factory.llm import LLMResponse, text_block, tool_use_block

# A valid Skills Report payload the fake research loop emits.
SAMPLE_REPORT = {
    "domain": "document summarization",
    "competencies": [
        "Extract key points from long documents",
        "Produce concise bullet-point summaries",
        "Preserve factual accuracy",
        "Handle multiple document formats",
    ],
    "tools_available": ["web_search", "calculator"],
    "tools_wishlist": [
        {
            "name": "pdf_extract",
            "purpose": "pull text out of PDF files",
            "external_dependency": "pdfminer",
        }
    ],
    "design_patterns": ["map-reduce summarization", "chunk-and-merge"],
    "sources": [
        {"url": "https://example.com/a", "title": "Summarization guide", "excerpt": "..."},
        {"url": "https://example.com/b", "title": "RAG patterns", "excerpt": "..."},
    ],
}

GENERATED_PROMPT = (
    "You are DocSummarizer, a specialist focused on turning lengthy material "
    "into clear, faithful bullet points. You excel at extracting the salient "
    "points from long inputs, compressing them without distorting meaning, and "
    "organizing the result for fast scanning. Use the web_search tool only when "
    "you need to confirm an external fact, and the calculator tool when a "
    "computation is required. Always preserve factual accuracy over brevity, "
    "and flag any uncertainty rather than inventing detail. Prefer a "
    "map-then-merge approach: summarize sections independently, then reconcile "
    "them into one coherent set of bullets."
)


def make_responder(report_payload: dict | None = None, generated_prompt: str | None = None):
    report_payload = report_payload or SAMPLE_REPORT
    generated_prompt = generated_prompt or GENERATED_PROMPT
    state = {"research_calls": 0}

    def responder(*, model, system, messages, tools, tool_choice):
        tool_names = {t["name"] for t in (tools or [])}

        # --- Tier 1: research loop ---------------------------------------- #
        if "emit_skills_report" in tool_names:
            state["research_calls"] += 1
            forced = bool(tool_choice and tool_choice.get("type") == "tool")
            if forced or state["research_calls"] >= 2:
                return LLMResponse(
                    "tool_use",
                    [tool_use_block("emit1", "emit_skills_report", report_payload)],
                )
            return LLMResponse(
                "tool_use",
                [tool_use_block("ws1", "web_search", {"query": "summarization best practices"})],
            )

        # --- Tier 2: system-prompt generation ----------------------------- #
        if "You write system prompts" in system:
            return LLMResponse("end_turn", [text_block(generated_prompt)])

        # --- Tier 5: a spawned ConfigDrivenAgent -------------------------- #
        has_tool_result = any(
            isinstance(m.get("content"), list)
            and any(b.get("type") == "tool_result" for b in m["content"])
            for m in messages
        )
        if "calculator" in tool_names and not has_tool_result:
            return LLMResponse(
                "tool_use",
                [tool_use_block("calc1", "calculator", {"expression": "2+2"})],
            )
        return LLMResponse("end_turn", [text_block("The answer is 4.")])

    return responder
