"""The generic, config-driven agent — Tier 2's bounded worker.

There is no bespoke class per agent: a *manifest* (system prompt, model, tool
allowlist, bounds) fully describes an agent, and one `Agent` class runs the
standard bounded tool-use loop for any of them. This is what Tier 6 will
hot-reload from disk — the manifest *is* the agent.

What this tier guarantees:
  * Least privilege  — the agent only ever sees the tools in its allowlist.
  * Bounded loops    — MAX_ITERATIONS caps the tool-use loop; on exhaustion it
                       returns a clean "didn't converge", never a hang.
  * Bounded calls    — max_tokens ceiling and a declared model per agent.

Deliberately *not* in this tier: boxing tool/sub-agent failures as data
(Tier 3) and the confirmation gate (Tier 4). Tool handlers are called directly
here; Tier 3 will wrap that boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .llm import LLM, DEFAULT_MODEL
from .registry import ToolRegistry, ToolView


@dataclass
class AgentManifest:
    """Everything needed to instantiate an agent — data, not code."""

    name: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    max_iterations: int = 8
    max_tokens: int = 4096
    effort: str = "high"


@dataclass
class AgentResult:
    agent: str
    output: str
    iterations: int
    converged: bool
    stop_reason: str | None = None


class Agent:
    """A manifest bound to a registry view and an LLM."""

    def __init__(
        self,
        manifest: AgentManifest,
        registry: ToolRegistry,
        llm: LLM | None = None,
    ) -> None:
        self.manifest = manifest
        # Resolve the allowlist into a filtered view now, so an invalid
        # manifest fails at construction rather than mid-run.
        self.tools: ToolView = registry.view(manifest.allowed_tools)
        # LLM is created lazily on first run so dry inspection (and tests)
        # don't require an API key.
        self._llm = llm

    def _ensure_llm(self) -> LLM:
        if self._llm is None:
            self._llm = LLM()
        return self._llm

    def run(self, task: str) -> AgentResult:
        m = self.manifest
        llm = self._ensure_llm()
        tool_schemas = self.tools.schemas()
        messages: list[dict] = [{"role": "user", "content": task}]
        last_stop: str | None = None

        for i in range(1, m.max_iterations + 1):
            response = llm.complete(
                model=m.model,
                system=m.system_prompt,
                messages=messages,
                tools=tool_schemas,
                max_tokens=m.max_tokens,
                effort=m.effort,
            )
            last_stop = response.stop_reason
            # Echo the full assistant turn back — including thinking blocks,
            # which the API requires to be preserved verbatim across turns.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return AgentResult(
                    agent=m.name,
                    output=_text_of(response),
                    iterations=i,
                    converged=True,
                    stop_reason=last_stop,
                )

            # Execute each requested tool and feed all results back in a single
            # user turn (the API expects one tool_result per tool_use, batched).
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool = self.tools.get(block.name)
                result = tool.handler(dict(block.input))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        # Loop exhausted without the model finishing — bounded, not hung.
        return AgentResult(
            agent=m.name,
            output=(
                f"[did not converge within {m.max_iterations} iterations]"
            ),
            iterations=m.max_iterations,
            converged=False,
            stop_reason=last_stop,
        )


def _text_of(response) -> str:
    """Concatenate the text blocks of a response into a plain string."""
    parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()
