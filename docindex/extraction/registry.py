"""Picks the extractor for a file from its extension."""

from collections.abc import Mapping
from pathlib import Path

from docindex.extraction.protocol import TextExtractor


class ExtractorRegistry:
    """A TextExtractor that hands each file to the extractor registered for its extension, ignoring case."""

    def __init__(self, extractors_by_extension: Mapping[str, TextExtractor]) -> None:
        self._extractors = {extension.lower(): extractor for extension, extractor in extractors_by_extension.items()}

    def extract(self, path: Path) -> str:
        """Return the clean text of `path`; raises KeyError for an extension with no extractor."""
        return self._extractors[path.suffix.lower()].extract(path)
