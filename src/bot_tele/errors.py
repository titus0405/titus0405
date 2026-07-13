"""Typed errors for the chat model client."""

from dataclasses import dataclass
from typing import override


@dataclass(frozen=True, slots=True)
class ModelError(Exception):
    """Raised when the model completion request fails."""

    message: str

    @override
    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class UnsupportedFileError(Exception):
    """Raised when an uploaded file has an extension we cannot parse."""

    message: str

    @override
    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class DocumentReadError(Exception):
    """Raised when a known file format fails to parse."""

    message: str

    @override
    def __str__(self) -> str:
        return self.message
