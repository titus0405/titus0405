import textwrap

from bot_tele.messages import TELEGRAM_MESSAGE_LIMIT, split_long_message


def test_short_text_returns_single_chunk() -> None:
    text = "halo dunia"
    assert split_long_message(text) == [text]


def test_empty_text_returns_single_empty_chunk() -> None:
    assert split_long_message("") == [""]


def test_text_at_limit_returns_single_chunk() -> None:
    text = "a" * TELEGRAM_MESSAGE_LIMIT
    result = split_long_message(text)
    assert result == [text]
    assert all(len(chunk) <= TELEGRAM_MESSAGE_LIMIT for chunk in result)


def test_text_one_char_over_limit_is_split_in_two() -> None:
    text = "a" * (TELEGRAM_MESSAGE_LIMIT + 1)
    result = split_long_message(text)
    assert len(result) == 2
    assert "".join(result) == text
    assert all(len(chunk) <= TELEGRAM_MESSAGE_LIMIT for chunk in result)


def test_multiline_text_splits_on_line_boundary() -> None:
    line = "a" * 10
    text = "\n".join([line] * 5)
    result = split_long_message(text, limit=12)
    assert len(result) == 5
    assert "".join(result) == text
    assert all(len(chunk) <= 12 for chunk in result)


def test_long_line_is_hard_split_when_no_newline_room() -> None:
    line = "b" * (TELEGRAM_MESSAGE_LIMIT * 2 + 5)
    text = f"header\n{line}\ntrailer"
    result = split_long_message(text)
    assert all(len(chunk) <= TELEGRAM_MESSAGE_LIMIT for chunk in result)
    assert "".join(result) == text
    assert result[0].startswith("header")
    assert result[-1].endswith("trailer")


def test_chunks_reassemble_to_original() -> None:
    text = textwrap.dedent(
        """\
        Pertama, kita bahas config.
        Kedua, kita jalankan bot.
        Ketiga, kita cek log.
        """
    ) * 200
    result = split_long_message(text)
    assert "".join(result) == text
    assert all(len(chunk) <= TELEGRAM_MESSAGE_LIMIT for chunk in result)
