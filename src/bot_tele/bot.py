"""Telegram bot wiring for the AI-backed assistant."""

import logging
from collections.abc import Awaitable, Callable, Sequence
from io import BytesIO
from typing import Final, Protocol

from telegram import Message, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .client import ChatClient
from .config import Settings, load_settings
from .conversation import ChatId, ChatMessage
from .documents import extract_text
from .errors import DocumentReadError, ModelError, UnsupportedFileError
from .events import ChatEvent, EventBus, EventType, now
from .knowledge import KnowledgeBase
from .messages import split_long_message
from .storage import LocalEventStore

logger = logging.getLogger(__name__)

WELCOME: Final = (
    "Halo! Saya bot yang terhubung dengan model AI.\n"
    "Kirim pesan apa saja, dan saya akan membalas.\n"
    "Unggah file (Excel, Word, PDF) untuk saya baca dan analisis.\n"
    "Gunakan /ask <pertanyaan> untuk bertanya langsung ke AI.\n"
    "Gunakan /reset untuk memulai percakapan baru, atau /help untuk bantuan."
)
RESET_NOTICE: Final = "Percakapan direset."
ERROR_NOTICE: Final = (
    "Maaf, terjadi gangguan saat menghubungi model AI. Coba lagi nanti."
)
FILE_READ_NOTICE: Final = (
    "✅ File '{name}' berhasil dibaca ({count} karakter). "
    "Silakan ajukan pertanyaan tentang isinya."
)
FILE_EMPTY_NOTICE: Final = (
    "⚠️ File '{name}' tidak berisi teks yang bisa diekstrak."
)
FILE_ERROR_NOTICE: Final = (
    "⚠️ Gagal membaca file '{name}'. Pastikan formatnya didukung "
    "(.xlsx, .xls, .docx, .pdf) dan file tidak rusak."
)
ASK_USAGE: Final = (
    "Gunakan: /ask <pertanyaan>\n"
    "Contoh: /ask apa poin utama dokumen yang saya unggah?"
)
HELP_TEXT: Final = (
    "Perintah yang tersedia:\n"
    "/start - mulai & reset percakapan\n"
    "/reset - hapus riwayat percakapan\n"
    "/ask - bertanya ke AI (contoh: /ask apa isi file?)\n"
    "/help - tampilkan pesan ini\n"
    "Kirim pesan apa saja untuk bercakap dengan AI.\n"
    "Unggah file Excel/Word/PDF untuk dibaca lalu ditanya isinya."
)
ADMIN_ONLY_NOTICE: Final = (
    "⛔ Akses ditolak. Hanya admin yang dapat mengunggah file ke bot ini."
)


class _ChatClient(Protocol):
    """Model backend contract so tests can inject a fake without network.

    Both the real `ChatClient` and any test double satisfy this structurally.
    """

    async def complete(
        self, messages: Sequence[ChatMessage], context: str = ""
    ) -> str: ...
    async def analyze_document(self, text: str, context: str = "") -> str: ...


def build_application(  # noqa: ANN201, C901, PLR0915
    settings: Settings, client: _ChatClient | None = None
):
    """Wire handlers to a local event store driven by an event bus.

    Every chat interaction is published as a `ChatEvent` to the bus; the
    `LocalEventStore` is the only subscriber and persists events to a
    local file. No chat content is sent to any external service.

    `client` is injectable so tests can supply a fake without network
    access. When omitted a real `ChatClient` is built from `settings`.

    Return type is the third-party `Application` generic whose data-type
    slots are not expressible without `Any`, so we let it be inferred.
    """
    store = LocalEventStore(settings.history_dir, settings.max_history)
    bus = EventBus()
    bus.subscribe(store)
    chat_client = client or ChatClient(settings)
    knowledge_base = KnowledgeBase()
    app = Application.builder().token(settings.telegram_token).build()

    async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        """Reset history and greet the user on /start."""
        if update.effective_chat is None or update.message is None:
            return
        chat_id = ChatId(update.effective_chat.id)
        bus.publish(ChatEvent(EventType.RESET, chat_id, "", now()))
        _ = await update.message.reply_text(WELCOME)

    async def reset(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear the chat's history on /reset."""
        if update.effective_chat is None or update.message is None:
            return
        chat_id = ChatId(update.effective_chat.id)
        bus.publish(ChatEvent(EventType.RESET, chat_id, "", now()))
        _ = await update.message.reply_text(RESET_NOTICE)

    async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show the list of available commands on /help."""
        if update.effective_chat is None or update.message is None:
            return
        _ = await update.message.reply_text(HELP_TEXT)

    async def _ask_model(
        chat_id: ChatId,
        question: str,
        reply: Callable[[str], Awaitable[Message]],
        context: str = "",
    ) -> None:
        """Run `question` through the model, persist events, and send the reply.

        `context` is the Dt/ passage retrieved for this question so the model
        answers from the official source.
        """
        bus.publish(ChatEvent(EventType.USER_MESSAGE, chat_id, question, now()))
        try:
            answer = await chat_client.complete(
                store.history(chat_id), context=context
            )
        except ModelError:
            logger.exception("Model request failed for chat %s", chat_id)
            bus.publish(ChatEvent(EventType.ERROR, chat_id, "model failure", now()))
            _ = await reply(ERROR_NOTICE)
            return
        bus.publish(ChatEvent(EventType.ASSISTANT_MESSAGE, chat_id, answer, now()))
        for part in split_long_message(answer):
            _ = await reply(part)

    async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Ground every reply in the Dt/ knowledge base, then answer directly."""
        if (
            update.effective_chat is None
            or update.message is None
            or update.message.text is None
        ):
            return
        chat_id = ChatId(update.effective_chat.id)
        _ = await context.bot.send_chat_action(
            chat_id=chat_id, action=ChatAction.TYPING
        )
        question = update.message.text
        kb_context = knowledge_base.retrieve(question)
        await _ask_model(
            chat_id, question, update.message.reply_text, kb_context
        )

    async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Ground the /ask question in the Dt/ knowledge base and answer directly."""
        if update.effective_chat is None or update.message is None:
            return
        chat_id = ChatId(update.effective_chat.id)
        args = context.args or []
        if not args:
            _ = await update.message.reply_text(ASK_USAGE)
            return
        question = " ".join(args)
        _ = await context.bot.send_chat_action(
            chat_id=chat_id, action=ChatAction.TYPING
        )
        kb_context = knowledge_base.retrieve(question)
        await _ask_model(chat_id, question, update.message.reply_text, kb_context)

    async def handle_document(  # noqa: PLR0911
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Read an uploaded document, load it into context, and analyze it."""
        if (
            update.effective_chat is None
            or update.message is None
            or update.message.document is None
        ):
            return
        chat_id = ChatId(update.effective_chat.id)
        user = update.effective_user
        if user is None or user.id not in settings.admin_ids:
            _ = await update.message.reply_text(ADMIN_ONLY_NOTICE)
            return
        document = update.message.document
        name = document.file_name or "file"
        _ = await context.bot.send_chat_action(
            chat_id=chat_id, action=ChatAction.TYPING
        )
        tg_file = await context.bot.get_file(document.file_id)
        buffer = BytesIO()
        await tg_file.download_to_memory(buffer)
        raw_bytes = buffer.getvalue()
        if not raw_bytes:
            _ = await update.message.reply_text(FILE_ERROR_NOTICE.format(name=name))
            return
        try:
            text = extract_text(document, raw_bytes)
        except UnsupportedFileError as e:
            _ = await update.message.reply_text(str(e))
            return
        except DocumentReadError as e:
            logger.warning("Failed to read document %s: %s", name, e)
            _ = await update.message.reply_text(FILE_ERROR_NOTICE.format(name=name))
            return
        if not text.strip():
            _ = await update.message.reply_text(FILE_EMPTY_NOTICE.format(name=name))
            return
        if len(text) > settings.max_file_chars:
            text = (
                text[: settings.max_file_chars]
                + "\n\n[...dipotong karena terlalu panjang...]"
            )
        payload = f"Berikut adalah isi file '{name}':\n\n{text}"
        bus.publish(ChatEvent(EventType.USER_MESSAGE, chat_id, payload, now()))
        _ = await update.message.reply_text(
            FILE_READ_NOTICE.format(name=name, count=len(text))
        )
        # Proactively analyze the document and surface the summary.
        _ = await context.bot.send_chat_action(
            chat_id=chat_id, action=ChatAction.TYPING
        )
        try:
            analysis = await chat_client.analyze_document(
                text, context=knowledge_base.retrieve(name)
            )
        except ModelError:
            logger.exception("Document analysis failed for chat %s", chat_id)
            bus.publish(
                ChatEvent(EventType.ERROR, chat_id, "analysis failure", now())
            )
            _ = await update.message.reply_text(ERROR_NOTICE)
            return
        bus.publish(ChatEvent(EventType.ASSISTANT_MESSAGE, chat_id, analysis, now()))
        for part in split_long_message(analysis):
            _ = await update.message.reply_text(part)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Document.ALL, respond
        )
    )
    return app


def main() -> None:
    """Entry point: configure logging and start long-polling."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    settings = load_settings()
    app = build_application(settings)
    _ = app.run_polling()
