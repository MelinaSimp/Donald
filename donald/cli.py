"""Donald's terminal interface — a streaming chat REPL."""

from __future__ import annotations

import os
import sys

import anthropic

from .persona import SYSTEM_PROMPT

MODEL = "claude-opus-4-8"
MAX_TOKENS = 4096

BANNER = """\
  ____                  _     _
 |  _ \\  ___  _ __   __ _| | __| |
 | | | |/ _ \\| '_ \\ / _` | |/ _` |
 | |_| | (_) | | | | (_| | | (_| |
 |____/ \\___/|_| |_|\\__,_|_|\\__,_|

 Donald — your terminal assistant.  Type /help for commands, /exit to leave.
"""

HELP = """\
Commands:
  /help    Show this help
  /reset   Forget the conversation and start fresh
  /exit    Quit (Ctrl-D or Ctrl-C also work)

Anything else you type is sent to Donald.
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


def _stream_reply(client: anthropic.Anthropic, messages: list[dict]) -> str:
    """Stream one assistant reply to stdout and return the full text."""
    print("Donald: ", end="", flush=True)
    parts: list[str] = []
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            parts.append(text)
            print(text, end="", flush=True)
    print("\n")
    return "".join(parts)


def main() -> None:
    """Run the interactive loop."""
    client = _build_client()
    messages: list[dict] = []
    print(BANNER)

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

        messages.append({"role": "user", "content": user_input})
        try:
            reply = _stream_reply(client, messages)
        except anthropic.APIStatusError as exc:
            messages.pop()  # don't keep a turn we couldn't answer
            print(f"\n[Donald hit an API error {exc.status_code}: {exc.message}]\n")
            continue
        except anthropic.APIConnectionError:
            messages.pop()
            print("\n[Network error reaching the API. Check your connection.]\n")
            continue
        messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
