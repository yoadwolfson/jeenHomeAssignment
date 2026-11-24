"""The fixed-size split strategy."""

from docindex.domain import MAX_CHUNK_CHARS

# 20% of the default size: long enough that a sentence near a cut appears whole in one chunk.
FIXED_OVERLAP_CHARS = 200


class FixedSizeChunker:
    """Cuts clean text into overlapping windows of at most `max_chars`, at whitespace."""

    def __init__(self, max_chars: int = MAX_CHUNK_CHARS, overlap_chars: int = FIXED_OVERLAP_CHARS) -> None:
        if max_chars <= 0:
            raise ValueError(f"max_chars must be positive, got {max_chars}")
        if not 0 <= overlap_chars < max_chars:
            raise ValueError(f"overlap_chars must be in [0, {max_chars}), got {overlap_chars}")
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars

    def split(self, clean_text: str) -> list[str]:
        """Return the stripped, non-empty chunks in document order; paragraph breaks are ignored."""
        chunks: list[str] = []
        start = _skip_whitespace(clean_text, 0)
        previous_end = start
        while start < len(clean_text):
            end = self._chunk_end(clean_text, start, previous_end)
            chunk = clean_text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(clean_text):
                break
            start = _skip_whitespace(clean_text, self._next_start(clean_text, start, end))
            previous_end = end
        return chunks

    def _chunk_end(self, text: str, start: int, previous_end: int) -> int:
        """The exclusive end of the chunk at `start`: the last whitespace in the window, else a hard cut."""
        limit = start + self._max_chars
        if limit >= len(text):
            return len(text)
        # A whitespace exactly at `limit` still lets the chunk fill the whole window. Cutting at or
        # before `previous_end` would make a chunk that only repeats the overlap, so hard-cut instead.
        for index in range(limit, max(start, previous_end), -1):
            if text[index].isspace():
                return index
        return limit

    def _next_start(self, text: str, start: int, end: int) -> int:
        """Where the next chunk begins: the first word boundary about the overlap amount back from `end`."""
        # Never step back to or before `start`, so every chunk makes progress.
        search_from = max(end - self._overlap_chars, start + 1)
        for index in range(search_from, end):
            if text[index].isspace():
                return index + 1
        return end


def _skip_whitespace(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position
