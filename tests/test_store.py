from pathlib import Path

from bot_tele.conversation import ChatId, ChatMessage, Role
from bot_tele.events import ChatEvent, EventBus, EventType, now
from bot_tele.storage import LocalEventStore

EVENTS_FILE: str = "chat_events.jsonl"


def _store(directory: Path) -> LocalEventStore:
    return LocalEventStore(directory, max_messages=5)


def _user(chat_id: int, text: str) -> ChatEvent:
    return ChatEvent(EventType.USER_MESSAGE, chat_id, text, now())


def _assistant(chat_id: int, text: str) -> ChatEvent:
    return ChatEvent(EventType.ASSISTANT_MESSAGE, chat_id, text, now())


def test_history_rebuilt_from_events(tmp_path: Path) -> None:
    store = _store(tmp_path)
    chat = ChatId(1)
    store.handle(_user(1, "hi"))
    store.handle(_assistant(1, "hello"))
    assert store.history(chat) == [
        ChatMessage(role=Role.USER, content="hi"),
        ChatMessage(role=Role.ASSISTANT, content="hello"),
    ]


def test_persists_to_local_file_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / EVENTS_FILE
    store = _store(tmp_path)
    store.handle(_user(1, "halo"))

    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    # Reloading from disk restores the same history (event sourcing).
    reloaded = LocalEventStore(tmp_path, max_messages=5)
    assert reloaded.history(ChatId(1)) == [
        ChatMessage(role=Role.USER, content="halo")
    ]


def test_reset_marks_history_cleared(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.handle(_user(1, "old"))
    store.handle(_assistant(1, "old reply"))
    store.handle(ChatEvent(EventType.RESET, 1, "", now()))
    store.handle(_user(1, "new"))
    assert store.history(ChatId(1)) == [
        ChatMessage(role=Role.USER, content="new")
    ]


def test_history_bounded_to_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(10):
        store.handle(_user(1, f"m{i}"))
    history = store.history(ChatId(1))
    assert len(history) == 5
    assert history[0]["content"] == "m5"


def test_bus_drives_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    bus = EventBus()
    bus.subscribe(store)
    bus.publish(_user(2, "via-bus"))
    assert store.history(ChatId(2)) == [
        ChatMessage(role=Role.USER, content="via-bus")
    ]


def test_error_events_excluded_from_history(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.handle(_user(1, "hi"))
    store.handle(ChatEvent(EventType.ERROR, 1, "model failure", now()))
    assert store.history(ChatId(1)) == [
        ChatMessage(role=Role.USER, content="hi")
    ]
