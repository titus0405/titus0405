"""Splitting long bot replies to fit Telegram's per-message length limit."""

from typing import Final

TELEGRAM_MESSAGE_LIMIT: Final = 4096


def split_long_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split `text` into chunks no longer than `limit` characters.

    The original text is preserved exactly when the chunks are concatenated
    (`"".join(split_long_message(text)) == text`). Boundaries prefer to break
    after a newline, then after a space, falling back to a hard cut only for
    runs with no break opportunity (e.g. a very long URL).
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        if len(text) - start <= limit:
            chunks.append(text[start:])
            break

        end = start + limit
        break_at = end
        newline = text.rfind("\n", start, end)
        space = text.rfind(" ", start, end)
        if newline > start:
            break_at = newline + 1
        elif space > start:
            break_at = space + 1
        chunks.append(text[start:break_at])
        start = break_at

    return chunks
