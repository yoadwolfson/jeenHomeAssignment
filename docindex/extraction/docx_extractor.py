"""DOCX text extraction with python-docx."""

from pathlib import Path

from docx import Document

from docindex.extraction.text_cleaner import TextCleaner


class DocxExtractor:
    """Reads a DOCX's body paragraphs in document order and hands them to the cleaner."""

    def __init__(self, cleaner: TextCleaner) -> None:
        self._cleaner = cleaner

    def extract(self, path: Path) -> str:
        """Return the DOCX's clean text; tables, headers, footers, footnotes and text boxes are excluded."""
        # Document.paragraphs holds only top-level body paragraphs, which is exactly the scope we index.
        return self._cleaner.clean_paragraphs(paragraph.text for paragraph in Document(str(path)).paragraphs)
