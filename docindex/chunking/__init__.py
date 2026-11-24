"""Splitting clean text into chunks."""

from docindex.chunking.factory import ChunkerFactory
from docindex.chunking.paragraph import ParagraphChunker
from docindex.chunking.protocol import Chunker

__all__ = ["Chunker", "ChunkerFactory", "ParagraphChunker"]
