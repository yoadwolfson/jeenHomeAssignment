"""Picks the extractor for a file from its extension."""

from collections.abc import Mapping
from pathlib import Path

from docindex.errors import MissingFileError, UnsupportedFileTypeError
from docindex.extraction.protocol import TextExtractor


class ExtractorRegistry:
    """A TextExtractor that hands each file to the extractor registered for its extension, ignoring case."""

    def __init__(self, extractors_by_extension: Mapping[str, TextExtractor]) -> None:
        self._extractors = {extension.lower(): extractor for extension, extractor in extractors_by_extension.items()}

    def extract(self, path: Path) -> str:
        """Return the clean text of `path`; raises MissingFileError or UnsupportedFileTypeError before any parsing."""
        if not path.is_file():
            raise MissingFileError(path)
        # The extension alone decides the type: no content sniffing, so a mislabelled file fails as unreadable.
        extractor = self._extractors.get(path.suffix.lower())
        if extractor is None:
            raise UnsupportedFileTypeError(path.suffix, list(self._extractors))
        return extractor.extract(path)
