"""The paragraph split strategy."""

from docindex.chunking.sentence import SentenceChunker
from docindex.chunking.sentence_splitter import SentenceSplitter
from docindex.domain import MAX_CHUNK_CHARS, paragraphs


class ParagraphChunker:
    """Makes one chunk per paragraph; only a paragraph over `max_chars` is divided, by sentence packing."""

    def __init__(self, splitter: SentenceSplitter, max_chars: int = MAX_CHUNK_CHARS) -> None:
        self._max_chars = max_chars
        # Built here from the same maximum, so the split threshold and the packing ceiling can't disagree.
        self._long_paragraph_chunker = SentenceChunker(splitter, max_chars=max_chars)

    def split(self, clean_text: str) -> list[str]:
        """Return each paragraph as its own chunk, or as sentence-packed chunks if it is too long."""
        chunks: list[str] = []
        for paragraph in paragraphs(clean_text):
            if len(paragraph) <= self._max_chars:
                chunks.append(paragraph)
                continue
            chunks.extend(self._long_paragraph_chunker.split(paragraph))
        return chunks
