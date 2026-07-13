from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import anyio
import pytest
from telegram import Bot, Chat, Message, Update, User
from telegram.ext import Application

from bot_tele.bot import build_application
from bot_tele.config import Settings
from bot_tele.references import ReferenceEntry, load_references, search_reference

DEFAULT_ADMINS: frozenset[int] = frozenset({43743281})


def _settings(admin_ids: frozenset[int] = DEFAULT_ADMINS) -> Settings:
    return Settings(
        telegram_token="dummy-token",
        openrouter_api_key="dummy-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_model="dummy-model",
        openrouter_referer="https://example.com",
        openrouter_title="Bot_Tele",
        history_dir=Path("data"),
        max_history=20,
        max_file_chars=50_000,
        admin_ids=admin_ids,
    )


class _RecordingClient:
    """Model backend that records when ``complete`` is called."""

    def __init__(self) -> None:
        self.complete_calls: list[object] = []

    async def complete(self, messages: object) -> str:
        self.complete_calls.append(messages)
        return "jawaban-model"

    async def analyze_document(self, text: str) -> str:
        _ = text
        return "ringkasan"


def _text_update(text: str, user_id: int = 43743281) -> Update:
    user = User(id=user_id, is_bot=False, first_name="U")
    chat = Chat(id=user_id, type="private")
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),  # noqa: UP017
        chat=chat,
        from_user=user,
        text=text,
    )
    return Update(update_id=1, message=message)


def _patch_bot_and_message(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncMock:
    """Neutralize frozen PTB objects and the init gate (see test_document)."""

    def _bypass_init_check(_self: object) -> None:
        return None

    monkeypatch.setattr(Bot, "send_chat_action", AsyncMock())
    monkeypatch.setattr(Application, "_check_initialized", _bypass_init_check)
    reply = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply)
    return reply


def _last_text(reply: AsyncMock) -> str:
    return cast("str", reply.call_args_list[-1].args[0])


# ─────────────────────────────────────────────────────────────────────
# Unit tests for the reference search itself
# ─────────────────────────────────────────────────────────────────────


def _sample_entries() -> list[ReferenceEntry]:
    return [
        ReferenceEntry(
            1, "Hipertensi", "K86", "I10", "Primer", "kriteria hipertensi berat"
        ),
        ReferenceEntry(
            2, "Diabetes Melitus", "T90", "E11", "Primer", "kriteria diabetes"
        ),
    ]


def test_search_reference_matches_diagnosis_name() -> None:
    entries = _sample_entries()
    result = search_reference("apa kriteria hipertensi", entries)
    assert result is not None
    assert result.diagnosis == "Hipertensi"


def test_search_reference_returns_none_without_overlap() -> None:
    entries = _sample_entries()
    assert search_reference("halo selamat pagi", entries) is None


def test_search_reference_respects_min_score() -> None:
    entries = _sample_entries()
    # "diabetes" scores 2 (one diagnosis hit x2); above min_score=5 it fails.
    assert search_reference("diabetes", entries, min_score=5) is None
    assert search_reference("diabetes", entries, min_score=2) is not None


def test_reference_entry_cites_source() -> None:
    entry = _sample_entries()[0]
    text = entry.to_text()
    assert "Hipertensi" in text
    assert "KMK" in text


def test_load_references_reads_real_workbook() -> None:
    entries = load_references()
    assert len(entries) > 0
    assert entries[0].diagnosis.strip() != ""


# ─────────────────────────────────────────────────────────────────────
# Integration tests for the ask-first flow through the bot
# ─────────────────────────────────────────────────────────────────────


def _fake_search_none(
    _question: str,
    _entries: list[ReferenceEntry],
    _min_score: int = 2,
) -> ReferenceEntry | None:
    return None


def _fake_search_match(
    _question: str,
    _entries: list[ReferenceEntry],
    _min_score: int = 2,
) -> ReferenceEntry:
    return _sample_entries()[0]


def test_question_in_reference_replies_from_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RecordingClient()
    monkeypatch.setattr("bot_tele.bot.load_references", list)
    monkeypatch.setattr("bot_tele.bot.search_reference", _fake_search_match)
    app = build_application(_settings(), client)
    reply = _patch_bot_and_message(monkeypatch)

    async def body() -> None:
        await app.process_update(_text_update("apa kriteria hipertensi"))

    anyio.run(body)

    assert "KMK" in _last_text(reply)
    # The model must NOT be consulted when the file has the answer.
    assert client.complete_calls == []


def test_question_not_in_reference_asks_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RecordingClient()
    monkeypatch.setattr("bot_tele.bot.load_references", list)
    monkeypatch.setattr("bot_tele.bot.search_reference", _fake_search_none)
    app = build_application(_settings(), client)
    reply = _patch_bot_and_message(monkeypatch)

    async def body() -> None:
        await app.process_update(_text_update("pertanyaan aneh sekali"))

    anyio.run(body)

    assert "Balas 'ya'" in _last_text(reply)
    assert client.complete_calls == []


def test_user_confirms_ya_queries_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RecordingClient()
    monkeypatch.setattr("bot_tele.bot.load_references", list)
    monkeypatch.setattr("bot_tele.bot.search_reference", _fake_search_none)
    app = build_application(_settings(), client)
    reply = _patch_bot_and_message(monkeypatch)

    async def body() -> None:
        await app.process_update(_text_update("pertanyaan aneh sekali"))
        await app.process_update(_text_update("ya"))

    anyio.run(body)

    assert client.complete_calls != []
    assert _last_text(reply) == "jawaban-model"


def test_user_declines_tidak_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RecordingClient()
    monkeypatch.setattr("bot_tele.bot.load_references", list)
    monkeypatch.setattr("bot_tele.bot.search_reference", _fake_search_none)
    app = build_application(_settings(), client)
    reply = _patch_bot_and_message(monkeypatch)

    async def body() -> None:
        await app.process_update(_text_update("pertanyaan aneh sekali"))
        await app.process_update(_text_update("tidak"))

    anyio.run(body)

    assert client.complete_calls == []
    assert "tidak diajukan" in _last_text(reply)
