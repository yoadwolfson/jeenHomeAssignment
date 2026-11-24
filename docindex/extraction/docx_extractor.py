"""DOCX text extraction with python-docx."""

from pathlib import Path

from docx import Document

from docindex.domain import PARAGRAPH_SEPARATOR


class DocxExtractor:
    """Reads a DOCX's body paragraphs in document order, keeping the non-empty ones."""

    def extract(self, path: Path) -> str:
        """Return the non-empty body paragraphs joined by blank lines."""
        paragraphs = (paragraph.text.strip() for paragraph in Document(str(path)).paragraphs)
        return PARAGRAPH_SEPARATOR.join(paragraph for paragraph in paragraphs if paragraph)
