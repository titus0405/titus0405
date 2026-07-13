from bot_tele.events import ChatEvent, EventBus, EventType, now


class _Handler:
    """Minimal `EventHandler` that records every event it receives."""

    def __init__(self) -> None:
        self.events: list[ChatEvent] = []

    def handle(self, event: ChatEvent) -> None:
        self.events.append(event)


def test_event_json_roundtrip() -> None:
    event = ChatEvent(EventType.USER_MESSAGE, 42, "halo", 1.5)
    assert ChatEvent.from_json(event.to_json()) == event


def test_event_persists_unicode() -> None:
    event = ChatEvent(EventType.ASSISTANT_MESSAGE, 1, " reply émoji 🚀 ", now())
    restored = ChatEvent.from_json(event.to_json())
    assert restored.text == " reply émoji 🚀 "


def test_bus_delivers_to_subscriber() -> None:
    bus = EventBus()
    handler = _Handler()
    bus.subscribe(handler)
    event = ChatEvent(EventType.ERROR, 7, "oops", now())
    bus.publish(event)
    assert handler.events == [event]


def test_bus_calls_handlers_in_order() -> None:
    bus = EventBus()
    order: list[str] = []

    class _Tagged:
        def __init__(self, tag: str) -> None:
            self._tag: str = tag

        def handle(self, event: ChatEvent) -> None:
            _ = event  # intentionally unused; we only track call order
            order.append(self._tag)

    bus.subscribe(_Tagged("a"))
    bus.subscribe(_Tagged("b"))
    bus.publish(ChatEvent(EventType.RESET, 1, "", now()))
    assert order == ["a", "b"]
