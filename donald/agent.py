"""The agent loop: brain ⇄ tools until Donald has a final answer.

This is the engine under both the text loop (Tier 0) and voice (Tier 2). Give
it a brain, a registry (possibly empty), and the running history; it asks the
brain for a move, runs any tools the brain requested, feeds the results back,
and repeats until the brain stops asking for tools. The final spoken/printed
text is returned.
"""

from __future__ import annotations

from typing import Any, Callable

from .brain import Brain, BrainResponse
from .tools.base import Registry

# Hard cap so a confused brain can't loop forever calling tools.
MAX_TOOL_ROUNDS = 8


class Agent:
    def __init__(
        self,
        brain: Brain,
        registry: Registry,
        system: str,
        on_tool: Callable[[str, dict[str, Any], str], None] | None = None,
    ):
        self.brain = brain
        self.registry = registry
        self.system = system
        # Optional observer for UI/logging: (tool_name, args, result).
        self.on_tool = on_tool

    def respond(self, messages: list[dict[str, Any]]) -> str:
        """Advance the conversation in-place and return Donald's reply text.

        ``messages`` is mutated: the assistant turn(s) and any tool results are
        appended, so the caller's history stays complete for the next turn.
        """
        tools = self.registry.schemas() if len(self.registry) else None

        for _ in range(MAX_TOOL_ROUNDS):
            response: BrainResponse = self.brain.complete(
                messages, tools=tools, system=self.system
            )

            # Record the assistant turn exactly as the model produced it.
            messages.append(
                {
                    "role": "assistant",
                    "content": response.raw_content
                    if response.raw_content is not None
                    else response.text,
                }
            )

            if not response.wants_tools:
                return response.text

            # Execute every requested tool and bundle the results into one
            # user turn (the protocol expects all tool_results together).
            tool_results = []
            for call in response.tool_calls:
                result = self.registry.dispatch(call.name, call.input)
                if self.on_tool:
                    self.on_tool(call.name, call.input, result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        return (
            "I got stuck running tools for that one — let me know if you'd like "
            "me to try a different way."
        )
