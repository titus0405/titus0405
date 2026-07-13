"""Reference knowledge base loaded from the KMK rujukan workbook.

The workbook ``Dt/Kriteria_Rujukan_KMK 1186 dan 1936.xlsx`` contains one
sheet (``Data``) of referral criteria keyed by diagnosis. At startup the
bot loads every row into :class:`ReferenceEntry` objects and answers
questions from this local source before falling back to the model.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import openpyxl

logger = logging.getLogger(__name__)

REFERENCE_PATH = Path("Dt/Kriteria_Rujukan_KMK 1186 dan 1936.xlsx")

SOURCE_FOOTER = (
    "Sumber: KMK HK.01.07/MENKES/1186/2022 & KMK HK.01.07/MENKES/1936/2022"
)

# Words that carry no diagnostic signal; excluded from overlap scoring so a
# question like "kriteria rujukan" does not match every row.
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


@dataclass(frozen=True)
class ReferenceEntry:
    """One referral-criteria row from the KMK workbook."""

    no: int
    diagnosis: str
    icpc2: str
    icd10: str
    capability: str
    criteria: str

    def to_text(self) -> str:
        """Render the entry as a chat reply with its source cited."""
        return (
            f"📋 {self.diagnosis}\n"
            f"ICPC-2: {self.icpc2}\n"
            f"ICD-10: {self.icd10}\n"
            f"Tingkat Kemampuan: {self.capability}\n\n"
            f"Kriteria Rujukan:\n{self.criteria}\n\n"
            f"{SOURCE_FOOTER}"
        )


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.casefold()


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", _normalize(text)) if t}


def load_references(path: Path | None = None) -> list[ReferenceEntry]:
    """Load every data row from the workbook into reference entries.

    Returns an empty list (logging a warning) when the workbook is missing
    so the bot still runs in environments without the KMK file.
    """
    path = path or REFERENCE_PATH
    if not path.exists():
        logger.warning("Reference workbook not found at %s", path)
        return []
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook.active
        if sheet is None:
            logger.warning("Reference workbook %s has no active sheet", path)
            return []
        rows = sheet.iter_rows(values_only=True)
        _ = next(rows, None)  # skip header
        entries: list[ReferenceEntry] = []
        for row in rows:
            if not row or row[0] is None:
                continue
            padded = (list(row) + [None] * 6)[:6]
            no, diagnosis, icpc2, icd10, capability, criteria = padded
            try:
                no_int = int(str(no))
            except (TypeError, ValueError):
                no_int = 0
            entries.append(
                ReferenceEntry(
                    no_int,
                    str(diagnosis or ""),
                    str(icpc2 or ""),
                    str(icd10 or ""),
                    str(capability or ""),
                    str(criteria or ""),
                )
            )
        return entries
    finally:
        workbook.close()


def search_reference(
    question: str,
    entries: list[ReferenceEntry],
    min_score: int = 2,
) -> ReferenceEntry | None:
    """Return the best-matching entry for ``question``, or ``None``.

    A diagnosis-name token match is weighted twice as strongly as a body
    match, so a question naming a condition is answered precisely.
    """
    query = _tokens(question) - _STOPWORDS
    if not query:
        return None
    best: ReferenceEntry | None = None
    best_score = 0
    for entry in entries:
        diagnosis_hits = len(query & (_tokens(entry.diagnosis) - _STOPWORDS)) * 2
        body_hits = len(
            query
            & (_tokens(entry.criteria) | _tokens(entry.icpc2) | _tokens(entry.icd10))
        )
        score = diagnosis_hits + body_hits
        if score > best_score:
            best_score = score
            best = entry
    if best is not None and best_score >= min_score:
        return best
    return None
