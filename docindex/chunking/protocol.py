"""The Chunker protocol shared by every split strategy."""

from typing import Protocol


class Chunker(Protocol):
    """Cuts clean text into chunks."""

    def split(self, clean_text: str) -> list[str]:
        """Return the non-empty, stripped chunks in document order."""
        ...
