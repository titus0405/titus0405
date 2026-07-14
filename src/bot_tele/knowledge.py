"""Lightweight retrieval-augmented grounding from the ``Dt/`` knowledge folder.

At startup every supported document in ``Dt/`` is extracted once, split into
overlapping chunks, and indexed by token. Each incoming question retrieves the
top-k most relevant chunks, which the model uses as its factual basis before
answering — so the bot stays grounded in the official KMK documents rather than
the model's general knowledge.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .documents import extract_text_from_bytes

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path("Dt")
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
TOP_K = 5

SUPPORTED_SUFFIXES: frozenset[str] = frozenset(
    {".xlsx", ".xlsm", ".xls", ".docx", ".pdf"}
)

# Words that carry no topical signal; excluded from overlap scoring so a vague
# question like "kriteria rujukan" does not match every chunk.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "dan",
        "atau",
        "untuk",
        "dengan",
        "yang",
        "pada",
        "di",
        "ke",
        "dari",
        "adalah",
        "kriteria",
        "rujukan",
        "apa",
        "bagaimana",
        "siapa",
        "kapan",
        "dimana",
        "mengapa",
        "kenapa",
        "ini",
        "itu",
        "saat",
        "jika",
        "maka",
        "serta",
        "akan",
        "telah",
        "sudah",
        "belum",
        "the",
        "a",
        "an",
        "of",
        "for",
        "to",
        "in",
        "on",
        "is",
        "are",
    }
)


@dataclass
class _Chunk:
    """One indexed slice of a knowledge document."""

    source: str
    index: int
    text: str
    tokens: frozenset[str]


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.casefold()


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", _normalize(text)) if t}


class KnowledgeBase:
    """In-memory retrieval index over the documents in ``Dt/``."""

    def __init__(self, directory: Path = KNOWLEDGE_DIR) -> None:
        self._chunks: list[_Chunk] = []
        self._load(directory)

    @property
    def loaded(self) -> bool:
        """Whether any document content was successfully indexed."""
        return bool(self._chunks)

    def _load(self, directory: Path) -> None:
        if not directory.exists():
            logger.warning("Knowledge folder %s not found", directory)
            return
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                raw = path.read_bytes()
                text = extract_text_from_bytes(path.name, raw)
            except Exception:
                logger.exception("Gagal membaca dokumen pengetahuan %s", path)
                continue
            if not text.strip():
                logger.info("Dokumen %s kosong, dilewati", path.name)
                continue
            self._index_file(path.name, text)
        logger.info(
            "Knowledge base dimuat: %d potongan dari %s",
            len(self._chunks),
            directory,
        )

    def _index_file(self, name: str, text: str) -> None:
        step = CHUNK_SIZE - CHUNK_OVERLAP
        start = 0
        index = 0
        while start < len(text):
            piece = text[start : start + CHUNK_SIZE]
            if piece.strip():
                self._chunks.append(
                    _Chunk(name, index, piece, frozenset(_tokenize(piece)))
                )
                index += 1
            start += step

    def retrieve(self, question: str, top_k: int = TOP_K) -> str:
        """Return the top-k most relevant chunks as a single context string.

        When no keyword overlaps, a few lead chunks are still returned so the
        model has a basis instead of falling back to general knowledge.
        """
        query = _tokenize(question) - _STOPWORDS
        if not query:
            return ""
        scored: list[tuple[int, _Chunk]] = []
        for chunk in self._chunks:
            overlap = len(query & chunk.tokens)
            if overlap > 0:
                scored.append((overlap, chunk))
        if scored:
            scored.sort(key=lambda item: item[0], reverse=True)
            selected = scored[:top_k]
        else:
            selected = [(0, chunk) for chunk in self._chunks[:top_k]]
        return "\n\n".join(
            f"[Sumber: {chunk.source}]\n{chunk.text}" for _, chunk in selected
        )
