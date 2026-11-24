"""The paragraph split strategy."""

from docindex.domain import PARAGRAPH_SEPARATOR


class ParagraphChunker:
    """Makes one chunk per paragraph of clean text."""

    def split(self, clean_text: str) -> list[str]:
        """Return each non-empty paragraph as its own chunk."""
        paragraphs = (paragraph.strip() for paragraph in clean_text.split(PARAGRAPH_SEPARATOR))
        return [paragraph for paragraph in paragraphs if paragraph]
