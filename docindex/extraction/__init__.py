"""Reading documents into clean text."""

from docindex.extraction.docx_extractor import DocxExtractor
from docindex.extraction.protocol import TextExtractor

__all__ = ["DocxExtractor", "TextExtractor"]
