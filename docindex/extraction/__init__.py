"""Reading documents into clean text."""

from docindex.extraction.docx_extractor import DocxExtractor
from docindex.extraction.pdf_extractor import PdfExtractor
from docindex.extraction.protocol import TextExtractor
from docindex.extraction.registry import ExtractorRegistry
from docindex.extraction.text_cleaner import TextCleaner

__all__ = ["DocxExtractor", "ExtractorRegistry", "PdfExtractor", "TextCleaner", "TextExtractor"]
