"""In-memory conversation store for the Donald agent.

The store holds clean history only — never the voice cue. ``messages_for_api``
returns fresh dicts so callers can mutate the API-bound copy (to append the
cue) without polluting what's persisted.
"""

from copy import deepcopy
from dataclasses import dataclass


@dataclass
class Message:
    role: str          # "user" or "assistant"
    content: object    # str, or a block-list for tool rounds


class ConversationManager:
    def __init__(self) -> None:
        self._messages: list[Message] = []

    def add_user_message(self, content) -> None:
        self._messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content) -> None:
        self._messages.append(Message(role="assistant", content=content))

    def messages_for_api(self) -> list[dict]:
        """Return a fresh list of plain dicts safe to mutate for the API call.

        Deep-copied so appending the voice cue to the returned list never
        touches stored history.
        """
        return [
            {"role": m.role, "content": deepcopy(m.content)}
            for m in self._messages
        ]

    @property
    def history(self) -> list[Message]:
        return list(self._messages)
