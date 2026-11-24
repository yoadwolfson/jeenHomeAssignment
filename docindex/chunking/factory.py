"""Maps a split strategy to its chunker."""

from collections.abc import Mapping

from docindex.chunking.protocol import Chunker
from docindex.domain import SplitStrategy


class ChunkerFactory:
    """Returns the chunker registered for a split strategy."""

    def __init__(self, chunkers: Mapping[SplitStrategy, Chunker]) -> None:
        self._chunkers = dict(chunkers)

    def for_strategy(self, strategy: SplitStrategy) -> Chunker:
        """Return the chunker for `strategy`; raises KeyError if none is registered."""
        return self._chunkers[strategy]
