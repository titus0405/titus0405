from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import anyio
import pytest
from telegram import Bot, Chat, Document, Message, Update, User
from telegram.ext import Application

from bot_tele.bot import build_application
from bot_tele.config import Settings

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


class _FakeClient:
    def __init__(self) -> None:
        self.analyzed: str | None = None

    async def complete(self, messages: object) -> str:
        _ = messages
        return "jawaban"

    async def analyze_document(self, text: str) -> str:
        self.analyzed = text
        return "ringkasan"


class _FakeFile:
    async def download_to_memory(self, buffer: BytesIO) -> None:
        _ = buffer.write(b"raw-bytes")


def _fake_extract(_doc: object, _raw: object) -> str:
    return "ISI FILE"


def _document_update(
    user_id: int = 43743281, caption: str | None = None
) -> Update:
    user = User(id=user_id, is_bot=False, first_name="U")
    chat = Chat(id=user_id, type="private")
    document = Document(file_id="f", file_unique_id="u", file_name="data.xlsx")
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),  # noqa: UP017
        chat=chat,
        from_user=user,
        document=document,
        caption=caption,
    )
    return Update(update_id=1, message=message)


def _patch_bot_and_message(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AsyncMock, _FakeFile]:
    """Replace frozen PTB methods at the class level.

    `Bot` and `Message` are frozen, so attributes cannot be assigned on
    instances. Patching the class (not frozen) lets the handler call the
    fakes. `process_update` requires the application to be initialized, but
    the bot/updater cannot reach the network in tests, so the init gate is
    neutralized at the class level. Returns the `reply_text` mock and the
    fake file so tests can assert on replies.
    """
    fake_file = _FakeFile()

    def _bypass_init_check(_self: object) -> None:
        return None

    monkeypatch.setattr(Bot, "get_file", AsyncMock(return_value=fake_file))
    monkeypatch.setattr(Bot, "send_chat_action", AsyncMock())
    monkeypatch.setattr(Application, "_check_initialized", _bypass_init_check)
    reply = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply)
    return reply, fake_file


def test_admin_upload_reads_and_analyzes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    client = _FakeClient()
    app = build_application(settings, client)
    reply, _ = _patch_bot_and_message(monkeypatch)
    monkeypatch.setattr("bot_tele.bot.extract_text", _fake_extract)

    update = _document_update()
    msg = update.message
    assert msg is not None

    async def body() -> None:
        await app.process_update(update)

    anyio.run(body)

    assert client.analyzed == "ISI FILE"
    assert reply.call_count >= 1


def test_non_admin_upload_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(admin_ids=frozenset({999}))
    client = _FakeClient()
    app = build_application(settings, client)
    reply, _ = _patch_bot_and_message(monkeypatch)
    monkeypatch.setattr("bot_tele.bot.extract_text", _fake_extract)

    update = _document_update(user_id=43743281)
    msg = update.message
    assert msg is not None

    async def body() -> None:
        await app.process_update(update)

    anyio.run(body)

    assert client.analyzed is None
    assert any(
        "Akses ditolak" in str(call.args)
        for call in reply.call_args_list
    )


def test_document_with_caption_is_not_swallowed_by_respond(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    client = _FakeClient()
    app = build_application(settings, client)
    _, _ = _patch_bot_and_message(monkeypatch)
    monkeypatch.setattr("bot_tele.bot.extract_text", _fake_extract)

    update = _document_update(caption="tolong baca file ini")
    msg = update.message
    assert msg is not None

    async def body() -> None:
        await app.process_update(update)

    anyio.run(body)

    # The document handler must run (not the text responder), so the file
    # gets analyzed rather than being forwarded to the model as a question.
    assert client.analyzed == "ISI FILE"
