"""Post-session summarization — the loop that turns a conversation into durable
memory (M2). After a session, a cheap model reads the transcript and returns
(a) durable facts about the user and (b) a short episodic summary. Both get
stored so the next session starts already knowing what happened.

The model is injected as a simple ``llm(prompt) -> str`` callable, so this stays
decoupled from any specific client and testable with a canned responder. With no
llm, it degrades to an offline heuristic (first-person facts + a terse summary)
so memory still improves without an API key.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

LLM = Callable[[str], str]

_PROMPT = """You are maintaining long-term memory for a personal assistant.
Read the conversation and return STRICT JSON with two keys:
  "facts": a list of durable, first-person-free statements about the user worth
           remembering across sessions (preferences, identity, ongoing projects).
           Omit anything transient or already obvious. Use [] if none.
  "summary": one or two sentences summarizing what happened this session.

Conversation:
{transcript}

Return ONLY the JSON object, nothing else."""

_FIRST_PERSON = re.compile(
    r"\b(i am|i'm|my |i prefer|i like|i love|i hate|i work|i live|i use|call me)\b",
    re.IGNORECASE,
)


def _render(transcript: list[dict]) -> str:
    lines = []
    for m in transcript:
        role = m.get("role", "?")
        content = m.get("content", "")
        if not isinstance(content, str):
            continue  # skip tool-call/blocks turns; we summarize spoken text
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model reply, tolerating chatter."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _heuristic(transcript: list[dict]) -> tuple[list[str], str]:
    facts: list[str] = []
    user_lines: list[str] = []
    for m in transcript:
        if m.get("role") != "user" or not isinstance(m.get("content"), str):
            continue
        line = m["content"].strip()
        user_lines.append(line)
        if _FIRST_PERSON.search(line):
            facts.append(re.split(r"[.!?\n]", line, maxsplit=1)[0].strip()[:200])
    summary = ""
    if user_lines:
        summary = "Session covered: " + "; ".join(user_lines[:3])[:280]
    # De-dupe facts, preserve order.
    seen, uniq = set(), []
    for f in facts:
        if f and f.lower() not in seen:
            seen.add(f.lower())
            uniq.append(f)
    return uniq, summary


def summarize_session(
    transcript: list[dict], llm: Optional[LLM] = None
) -> tuple[list[str], str]:
    """Return ``(facts, episode_summary)`` for a session transcript."""
    if not transcript:
        return [], ""
    if llm is None:
        return _heuristic(transcript)
    try:
        raw = llm(_PROMPT.format(transcript=_render(transcript)))
        parsed = _parse_json(raw)
        if parsed is None:
            return _heuristic(transcript)
        facts = [str(f).strip() for f in parsed.get("facts", []) if str(f).strip()]
        summary = str(parsed.get("summary", "")).strip()
        return facts[:20], summary[:500]
    except Exception:
        # A model hiccup must never lose the session — fall back.
        return _heuristic(transcript)
