"""The Donald agent loop.

Wires the personality-persistence layers into an Anthropic API call:
  - cached system block carries AGENT.md
  - uncached system block carries the per-turn tonal checkpoint
  - the voice cue is appended to the API-bound messages only

Run interactively with:  python -m donald.agent
(requires ANTHROPIC_API_KEY in the environment)
"""

import os

from .conversation import ConversationManager
from .personality import append_voice_cue, build_system_prompt, load_personality

MODEL = "claude-opus-4-8"
MAX_TOKENS = 1024
TEMPERATURE = 0.8  # a touch of heat keeps the swagger from flattening out


def respond(client, conversation: ConversationManager, personality_text: str) -> str:
    """Run one turn: build the payload, call the model, store the clean reply."""
    messages = conversation.messages_for_api()  # fresh, mutable copy
    append_voice_cue(messages)                   # API-only mutation
    system = build_system_prompt(personality_text)

    response = client.messages.create(
        model=MODEL,
        system=system,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    conversation.add_assistant_message(text)     # stored clean, no cue
    return text


def main() -> None:
    from anthropic import Anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY to talk to Donald.")

    client = Anthropic()
    conversation = ConversationManager()
    personality_text = load_personality()

    print("Donald is in the building. The best building. (Ctrl-C to leave.)\n")
    try:
        while True:
            user = input("you> ").strip()
            if not user:
                continue
            conversation.add_user_message(user)
            reply = respond(client, conversation, personality_text)
            print(f"\nDonald> {reply}\n")
    except (KeyboardInterrupt, EOFError):
        print("\nDonald> Smart move leaving on a high note. Tremendous exit.")


if __name__ == "__main__":
    main()
