"""PDF text extraction with pypdf."""

from pathlib import Path
from typing import Final, Literal

from pypdf import PdfReader

from docindex.errors import UnreadableDocumentError
from docindex.extraction.text_check import require_extractable_text
from docindex.extraction.text_cleaner import TextCleaner

# Plain mode drops the vertical gaps that are the only paragraph signal in a PDF.
EXTRACTION_MODE: Final[Literal["layout"]] = "layout"


class PdfExtractor:
    """Reads a PDF page by page in layout mode and hands the raw text to the cleaner."""

    def __init__(self, cleaner: TextCleaner) -> None:
        self._cleaner = cleaner

    def extract(self, path: Path) -> str:
        """Return the PDF's clean text; a page break always ends a paragraph."""
        clean_text = self._cleaner.clean_pages(_read_page_texts(path))
        # A PDF with pages but no text layer is usually a scan, so the message points at OCR.
        return require_extractable_text(clean_text, path, may_be_scanned=True)


def _read_page_texts(path: Path) -> list[str]:
    # Only pypdf runs inside the try: on malformed input it raises its own errors but also KeyError, ValueError,
    # zlib errors and more, so anything it raises means "cannot parse". Our cleaner stays outside, so its bugs still
    # surface as unexpected failures. An encrypted PDF opens fine and fails only here, at text extraction.
    try:
        reader = PdfReader(path)
        return [page.extract_text(extraction_mode=EXTRACTION_MODE) for page in reader.pages]
    except Exception as error:
        raise UnreadableDocumentError(path.name) from error
