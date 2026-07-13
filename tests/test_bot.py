from pathlib import Path

from telegram.ext import CommandHandler, MessageHandler

from bot_tele.bot import build_application
from bot_tele.config import Settings


def _dummy_settings() -> Settings:
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


def test_build_application_registers_expected_handlers() -> None:
    app = build_application(_dummy_settings())

    commands: set[str] = set()
    has_message_handler = False
    for group in app.handlers.values():
        for handler in group:
            if isinstance(handler, CommandHandler):
                commands.update(handler.commands)
            elif isinstance(handler, MessageHandler):
                has_message_handler = True

    assert commands == {"start", "reset", "help", "ask"}
    assert has_message_handler
