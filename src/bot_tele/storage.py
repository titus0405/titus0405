"""Local-only, append-only, event-sourced chat history store.

History is persisted to a JSONL file inside a local directory. Nothing is
sent to any external service: the on-disk event log is the single source
of truth, and an in-memory index provides fast history lookups. The store
acts as an `EventHandler` so it is driven entirely by the `EventBus`.
"""

from pathlib import Path
from typing import Final

from .conversation import ChatId, ChatMessage, Role
from .events import ChatEvent, EventType

EVENTS_FILENAME: Final = "chat_events.jsonl"


class LocalEventStore:
    """Persist chat events locally and serve history from the event log."""

    def __init__(self, directory: Path, max_messages: int = 20) -> None:
        """Open (or create) the local event log under `directory`."""
        self._directory: Path = directory
        self._max: int = max_messages
        self._path: Path = directory / EVENTS_FILENAME
        self._by_chat: dict[int, list[ChatEvent]] = {}
        self._directory.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        """Rebuild the in-memory index from the on-disk event log."""
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                self._append_index(ChatEvent.from_json(line))

    def _append_index(self, event: ChatEvent) -> None:
        self._by_chat.setdefault(event.chat_id, []).append(event)

    def handle(self, event: ChatEvent) -> None:
        """Persist an event to the local log (invoked by the `EventBus`)."""
        self._append_index(event)
        with self._path.open("a", encoding="utf-8") as fh:
            _ = fh.write(event.to_json() + "\n")

    def history(self, chat_id: ChatId) -> list[ChatMessage]:
        """Rebuild the chat's message history from its event log.

        Events before the most recent RESET are ignored, and the result
        is bounded to the most recent `max_messages`.
        """
        events = self._by_chat.get(int(chat_id), [])
        start = 0
        for index, event in enumerate(events):
            if event.event_type == EventType.RESET:
                start = index + 1
        messages: list[ChatMessage] = []
        for event in events[start:]:
            if event.event_type == EventType.USER_MESSAGE:
                messages.append(ChatMessage(role=Role.USER, content=event.text))
            elif event.event_type == EventType.ASSISTANT_MESSAGE:
                messages.append(ChatMessage(role=Role.ASSISTANT, content=event.text))
        if len(messages) > self._max:
            messages = messages[-self._max:]
        return messages
