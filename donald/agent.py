"""Tier 1 — the agent loop.

The conductor that turns a conversation into Donald's next move. It holds a
``Brain`` (Tier 0, the model) and a ``Registry`` (the tools) and runs the
tool-use loop: ask the brain, run any tools it asks for, feed the results back,
repeat until the brain answers in words.

Everything upstream (the text REPL, the voice loop, the proactive daemon) drives
the same ``Agent.respond`` — the loop is written once, here. The brain interface
is model-agnostic, so swapping ``MockBrain`` for ``ClaudeBrain`` (or another
model) changes nothing in this file.

    from donald.app import build
    donald = build()
    reply = donald.agent.respond([{"role": "user", "content": "what time is it?"}])
"""

from __future__ import annotations

from typing import Any

from .brain import Brain

# A hard ceiling on tool round-trips in a single turn, so a brain that keeps
# asking for tools (or a mock that misbehaves) can never hang the loop.
MAX_TOOL_ITERATIONS = 8


class Agent:
    """One turn of conversation, tools and all.

    Parameters
    ----------
    brain:
        Anything implementing ``Brain.complete(messages, tools, system)``.
    registry:
        The tool ``Registry`` — its ``schemas()`` are offered to the brain and
        its ``dispatch()`` runs the calls the brain makes (through the safety
        gate, if one is installed).
    system:
        The system prompt for this agent (persona + any injected memory).
    max_iterations:
        Cap on tool round-trips per ``respond`` call.
    """

    def __init__(
        self,
        brain: Brain,
        registry: Any,
        system: str = "",
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self.brain = brain
        self.registry = registry
        self.system = system
        self.max_iterations = max_iterations

    def respond(self, messages: list[dict[str, Any]]) -> str:
        """Run one turn to completion, mutating ``messages`` in place.

        Appends the assistant's turns (and any tool round-trips) to ``messages``
        and returns the final spoken text. The last message is always the
        assistant's answer, so the caller can persist ``messages`` as the
        running transcript.
        """
        tools = self.registry.schemas()

        for _ in range(self.max_iterations):
            response = self.brain.complete(messages, tools=tools, system=self.system)

            if response.wants_tools:
                # Record the assistant's tool-use turn verbatim (the Anthropic
                # protocol requires the exact content blocks back in history),
                # then run each call and feed the results in as one user turn.
                messages.append(
                    {"role": "assistant", "content": response.raw_content or []}
                )
                results = []
                for call in response.tool_calls:
                    output = self.registry.dispatch(call.name, call.input)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": output,
                        }
                    )
                messages.append({"role": "user", "content": results})
                continue

            text = response.text or ""
            messages.append({"role": "assistant", "content": text})
            return text

        # Didn't converge within the tool-iteration budget: return a clean,
        # honest message rather than looping forever.
        text = (
            "I got stuck taking too many steps on that one. Let's try again with "
            "a smaller ask."
        )
        messages.append({"role": "assistant", "content": text})
        return text
