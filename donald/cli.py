"""Donald's terminal interface — a streaming, tool-using agent REPL."""

from __future__ import annotations

import os
import sys

import anthropic

from . import config, memory, tools, voice
from .persona import SYSTEM_PROMPT

BANNER = """\
  ____                  _     _
 |  _ \\  ___  _ __   __ _| | __| |
 | | | |/ _ \\| '_ \\ / _` | |/ _` |
 | |_| | (_) | | | | (_| | | (_| |
 |____/ \\___/|_| |_|\\__,_|_|\\__,_|

 Donald — your terminal assistant.  Type /help for commands, /exit to leave.
 Tools: read/write/edit files, run_shell, web_search, remember (edits & shell ask first).
"""

HELP = """\
Commands:
  /help    Show this help
  /reset   Forget the current conversation and start fresh
  /memory  Show what Donald remembers across sessions
  /forget  Wipe Donald's long-term memory
  /voice   Toggle spoken replies (needs the `voice` extra)
  /exit    Quit (Ctrl-D or Ctrl-C also work)

Anything else you type is sent to Donald. He can read, write, and edit files,
run shell commands, search the web, and remember durable facts about you
between sessions — he'll ask before editing files or running shell.
"""


def _build_client() -> anthropic.Anthropic:
    """Create the Anthropic client, failing clearly if the key is missing."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY is not set.\n"
            "Get a key at https://console.anthropic.com/ and run:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "or copy .env.example to .env and fill it in."
        )
    return anthropic.Anthropic()


def _approved(name: str, args: dict) -> bool:
    """Ask the operator to approve a machine-changing tool call."""
    try:
        answer = input(f"  allow {tools.describe(name, args)} ? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def _run_tool_calls(blocks: list) -> list[dict]:
    """Execute the tool_use blocks in an assistant turn; return tool_result blocks."""
    results: list[dict] = []
    for block in blocks:
        if getattr(block, "type", None) != "tool_use":
            continue  # skip text and any server-side tool blocks
        print(f"  ↳ {tools.describe(block.name, block.input)}")
        needs_approval = (
            block.name in tools.REQUIRES_APPROVAL
            and not tools.auto_approved(block.name, block.input)
        )
        if needs_approval and not _approved(block.name, block.input):
            content, is_error = "Operator declined this action.", True
        else:
            content, is_error = tools.execute(block.name, block.input)
        results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
                "is_error": is_error,
            }
        )
    return results


def _agent_turn(
    client: anthropic.Anthropic,
    messages: list[dict],
    system: str,
    cfg: config.Config,
    speaker: voice.Speaker,
) -> None:
    """Run one full turn: stream replies and loop through any tool use."""
    print("Donald: ", end="", flush=True)
    while True:
        with client.messages.stream(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            system=system,
            tools=tools.ALL_TOOLS,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            message = stream.get_final_message()
        print()
        messages.append({"role": "assistant", "content": message.content})

        # Read any prose aloud (no-op unless voice is on).
        spoken = "".join(
            b.text for b in message.content if getattr(b, "type", None) == "text"
        )
        speaker.speak(spoken)

        if message.stop_reason == "tool_use":
            tool_results = _run_tool_calls(message.content)
            messages.append({"role": "user", "content": tool_results})
            continue
        if message.stop_reason == "pause_turn":
            # Server-side tool (web search) hit its loop limit — resume.
            continue
        return


def main() -> None:
    """Run the interactive loop."""
    cfg = config.load()
    client = _build_client()
    messages: list[dict] = []
    # Load remembered facts once at startup, the way a person reviews their
    # notes before getting to work. New memories apply next session.
    system = SYSTEM_PROMPT + memory.block()
    speaker = voice.Speaker(enabled=cfg.voice or "--voice" in sys.argv)
    print(BANNER)
    if speaker.enabled:
        print("(spoken replies on)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return

        if not user_input:
            continue

        if user_input in ("/exit", "/quit"):
            print("Goodbye.")
            return
        if user_input == "/help":
            print(HELP)
            continue
        if user_input == "/reset":
            messages.clear()
            print("(conversation cleared)\n")
            continue
        if user_input == "/memory":
            current = memory.load().strip()
            print(f"\n{current}\n" if current else "(nothing remembered yet)\n")
            continue
        if user_input == "/forget":
            had = memory.clear()
            system = SYSTEM_PROMPT  # this session stops referencing the old notes
            print("(memory wiped)\n" if had else "(nothing to forget)\n")
            continue
        if user_input == "/voice":
            _, note = speaker.toggle()
            print(f"({note})\n")
            continue
        if user_input == "/listen":
            spoken, note = voice.listen_once()
            if not spoken:
                print(f"({note})\n")
                continue
            print(f"You (spoken): {spoken}")
            user_input = spoken  # fall through and send it as this turn's message

        checkpoint = len(messages)  # roll back to here if the turn fails
        messages.append({"role": "user", "content": user_input})
        try:
            _agent_turn(client, messages, system, cfg, speaker)
            print()
        except anthropic.APIStatusError as exc:
            del messages[checkpoint:]  # drop the failed turn so history stays valid
            print(f"\n[Donald hit an API error {exc.status_code}: {exc.message}]\n")
        except anthropic.APIConnectionError:
            del messages[checkpoint:]
            print("\n[Network error reaching the API. Check your connection.]\n")


if __name__ == "__main__":
    main()
