"""Domain events and a minimal synchronous event bus for chat history.

The bot records every chat interaction as an immutable `ChatEvent`. Events
are dispatched through an `EventBus` to subscribed handlers. By design,
all persistence happens locally (see `storage.LocalEventStore`); nothing
in this module sends chat content to any external service.
"""

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast, runtime_checkable


class EventType(StrEnum):
    """Kinds of chat events worth recording locally."""

    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    ERROR = "error"
    RESET = "reset"


@dataclass(frozen=True, slots=True)
class ChatEvent:
    """An immutable record of something that happened in a chat."""

    event_type: EventType
    chat_id: int
    text: str
    timestamp: float

    def to_json(self) -> str:
        """Serialize to a single UTF-8-safe JSON line."""
        return json.dumps(
            {
                "event_type": self.event_type.value,
                "chat_id": self.chat_id,
                "text": self.text,
                "timestamp": self.timestamp,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, line: str) -> "ChatEvent":
        """Parse a JSON line produced by `to_json`."""
        data = cast("dict[str, object]", json.loads(line))
        return cls(
            event_type=EventType(cast("str", data["event_type"])),
            chat_id=int(cast("int", data["chat_id"])),
            text=cast("str", data["text"]),
            timestamp=float(cast("float", data["timestamp"])),
        )


@runtime_checkable
class EventHandler(Protocol):
    """Anything that can react to a published `ChatEvent`."""

    def handle(self, event: ChatEvent) -> None:
        """React to a published event."""
        ...


class EventBus:
    """Synchronous publish/subscribe dispatcher for `ChatEvent`s."""

    def __init__(self) -> None:
        """Create an empty, subscriber-less bus."""
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        """Register a handler that receives every published event."""
        self._handlers.append(handler)

    def publish(self, event: ChatEvent) -> None:
        """Deliver `event` to all subscribed handlers, in registration order."""
        for handler in self._handlers:
            handler.handle(event)


def now() -> float:
    """Current Unix timestamp, used as the event time."""
    return time.time()
