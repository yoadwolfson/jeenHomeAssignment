"""The ChunkRepository protocol the services depend on."""

from typing import Protocol

from docindex.domain import ChunkRecord, SearchResult, SplitStrategy


class ChunkRepository(Protocol):
    """Stores chunk sets per (filename, strategy) and finds the most similar chunks."""

    def ensure_schema(self) -> None:
        """Create the extension, table and index if they don't exist yet."""
        ...

    def replace_chunks(self, filename: str, strategy: SplitStrategy, records: list[ChunkRecord]) -> None:
        """Atomically replace the stored chunks for (filename, strategy) with `records`."""
        ...

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        """Return up to `top_k` stored chunks, most similar to `vector` first."""
        ...
