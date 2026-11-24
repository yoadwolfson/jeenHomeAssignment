"""Splitting clean text into chunks."""

from docindex.chunking.factory import ChunkerFactory
from docindex.chunking.fixed import FixedSizeChunker
from docindex.chunking.paragraph import ParagraphChunker
from docindex.chunking.protocol import Chunker
from docindex.chunking.sentence import SentenceChunker
from docindex.chunking.sentence_splitter import PysbdSentenceSplitter, SentenceSplitter

__all__ = [
    "Chunker",
    "ChunkerFactory",
    "FixedSizeChunker",
    "ParagraphChunker",
    "PysbdSentenceSplitter",
    "SentenceChunker",
    "SentenceSplitter",
]
