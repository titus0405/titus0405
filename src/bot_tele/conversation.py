"""Per-chat conversation history for the LLM context window."""

from enum import StrEnum
from typing import Final, NewType, TypedDict

ChatId = NewType("ChatId", int)

MAX_HISTORY_MESSAGES: Final = 20


class Role(StrEnum):
    """Participant of a single chat message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(TypedDict):
    """A single chat message in the LLM conversation history."""

    role: Role
    content: str


class ConversationStore:
    """Per-chat rolling message history for the LLM context window.

    Mutable by design: it accumulates messages across turns until reset.
    """

    def __init__(self, max_messages: int = MAX_HISTORY_MESSAGES) -> None:
        """Cap retained messages per chat at `max_messages`."""
        self._max: int = max_messages
        self._histories: dict[ChatId, list[ChatMessage]] = {}

    def add(self, chat_id: ChatId, role: Role, content: str) -> None:
        """Append a message, keeping only the most recent window."""
        history = self._histories.setdefault(chat_id, [])
        history.append(ChatMessage(role=role, content=content))
        if len(history) > self._max:
            del history[: len(history) - self._max]

    def history(self, chat_id: ChatId) -> list[ChatMessage]:
        """Return a copy of the chat's history (never the internal list)."""
        return list(self._histories.get(chat_id, []))

    def reset(self, chat_id: ChatId) -> None:
        """Forget all history for a chat."""
        if chat_id in self._histories:
            del self._histories[chat_id]
