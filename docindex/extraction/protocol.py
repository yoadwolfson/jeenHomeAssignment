"""The TextExtractor protocol the indexing service depends on."""

from pathlib import Path
from typing import Protocol


class TextExtractor(Protocol):
    """Reads one document format into clean text."""

    def extract(self, path: Path) -> str:
        """Return the document's clean text: paragraphs separated by exactly one blank line."""
        ...
