"""PDF text extraction with pypdf."""

from pathlib import Path
from typing import Final, Literal

from pypdf import PdfReader

from docindex.extraction.text_cleaner import TextCleaner

# Plain mode drops the vertical gaps that are the only paragraph signal in a PDF.
EXTRACTION_MODE: Final[Literal["layout"]] = "layout"


class PdfExtractor:
    """Reads a PDF page by page in layout mode and hands the raw text to the cleaner."""

    def __init__(self, cleaner: TextCleaner) -> None:
        self._cleaner = cleaner

    def extract(self, path: Path) -> str:
        """Return the PDF's clean text; a page break always ends a paragraph."""
        reader = PdfReader(path)
        return self._cleaner.clean_pages(page.extract_text(extraction_mode=EXTRACTION_MODE) for page in reader.pages)
