"""The sentence split strategy."""

from docindex.chunking.fixed import FixedSizeChunker
from docindex.chunking.sentence_splitter import SentenceSplitter
from docindex.domain import MAX_CHUNK_CHARS, paragraphs

SENTENCE_JOINER = " "


class SentenceChunker:
    """Packs whole sentences into chunks of at most `max_chars`, across paragraph boundaries."""

    def __init__(self, splitter: SentenceSplitter, max_chars: int = MAX_CHUNK_CHARS) -> None:
        self._splitter = splitter
        self._max_chars = max_chars
        # Only a sentence longer than the maximum is cut, so it gets no overlap: sentence chunks never repeat text.
        self._long_sentence_chunker = FixedSizeChunker(max_chars=max_chars, overlap_chars=0)

    def split(self, clean_text: str) -> list[str]:
        """Return the packed chunks in document order; a sentence over the maximum is cut at whitespace."""
        chunks: list[str] = []
        pending_chunk = ""
        for sentence in self._sentences(clean_text):
            if len(sentence) > self._max_chars:
                if pending_chunk:
                    chunks.append(pending_chunk)
                chunks.extend(self._long_sentence_chunker.split(sentence))
                pending_chunk = ""
                continue
            candidate = f"{pending_chunk}{SENTENCE_JOINER}{sentence}" if pending_chunk else sentence
            if len(candidate) <= self._max_chars:
                pending_chunk = candidate
                continue
            chunks.append(pending_chunk)
            pending_chunk = sentence
        if pending_chunk:
            chunks.append(pending_chunk)
        return chunks

    def _sentences(self, clean_text: str) -> list[str]:
        # One paragraph at a time, so no sentence spans paragraphs and a heading with no final period
        # never merges into the next sentence, whatever the splitter does with line breaks.
        return [sentence for paragraph in paragraphs(clean_text) for sentence in self._splitter.split(paragraph)]
