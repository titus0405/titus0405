from pathlib import Path

import anyio
import pytest
from openai.types.chat import ChatCompletionMessageParam

from bot_tele.client import ChatClient
from bot_tele.config import Settings
from bot_tele.conversation import ChatMessage, Role


def _settings() -> Settings:
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
        admin_ids=frozenset(),
    )


def test_analyze_document_returns_model_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ChatClient(_settings())

    async def fake_request(_payload: list[ChatCompletionMessageParam]) -> str:
        return "ringkasan dokumen"

    monkeypatch.setattr(client, "_request", fake_request)
    result = anyio.run(client.analyze_document, "isi dokumen")
    assert result == "ringkasan dokumen"


def test_complete_returns_model_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ChatClient(_settings())

    async def fake_request(_payload: list[ChatCompletionMessageParam]) -> str:
        return "jawaban"

    monkeypatch.setattr(client, "_request", fake_request)
    result = anyio.run(
        client.complete, [ChatMessage(role=Role.USER, content="hai")]
    )
    assert result == "jawaban"
