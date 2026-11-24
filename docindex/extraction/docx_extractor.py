"""DOCX text extraction with python-docx."""

from pathlib import Path

from docx import Document

from docindex.errors import UnreadableDocumentError
from docindex.extraction.text_check import require_extractable_text
from docindex.extraction.text_cleaner import TextCleaner


class DocxExtractor:
    """Reads a DOCX's body paragraphs in document order and hands them to the cleaner."""

    def __init__(self, cleaner: TextCleaner) -> None:
        self._cleaner = cleaner

    def extract(self, path: Path) -> str:
        """Return the DOCX's clean text; tables, headers, footers, footnotes and text boxes are excluded."""
        clean_text = self._cleaner.clean_paragraphs(_read_paragraph_texts(path))
        return require_extractable_text(clean_text, path, may_be_scanned=False)


def _read_paragraph_texts(path: Path) -> list[str]:
    # Only python-docx runs inside the try: a damaged package can fail with zipfile, lxml or KeyError errors as well
    # as its own, and every one of them means "cannot parse". Our cleaner stays outside, so its bugs are not hidden.
    try:
        # Document.paragraphs holds only top-level body paragraphs, which is exactly the scope we index.
        return [paragraph.text for paragraph in Document(str(path)).paragraphs]
    except Exception as error:
        raise UnreadableDocumentError(path.name) from error
