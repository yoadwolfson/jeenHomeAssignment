"""Value types and constants shared across the package."""

from dataclasses import dataclass
from enum import StrEnum

EMBEDDING_DIMENSIONS = 1536
DEFAULT_TOP_K = 5
# Shared ceiling for every split strategy; ~250 English tokens, far under Gemini's 2,048-token input limit.
MAX_CHUNK_CHARS = 1000
# The only paragraph separator in clean text.
PARAGRAPH_SEPARATOR = "\n\n"


class SplitStrategy(StrEnum):
    """The rule used to cut clean text into chunks."""

    fixed = "fixed"
    sentence = "sentence"
    paragraph = "paragraph"


@dataclass(frozen=True)
class ChunkRecord:
    """One embedded chunk, ready to be stored."""

    filename: str
    strategy: SplitStrategy
    chunk_index: int
    text: str
    embedding: list[float]


@dataclass(frozen=True)
class SearchResult:
    """One stored chunk returned for a query, with its cosine similarity."""

    filename: str
    strategy: SplitStrategy
    chunk_index: int
    text: str
    score: float


@dataclass(frozen=True)
class IndexingReport:
    """What one indexing run stored."""

    filename: str
    strategy: SplitStrategy
    chunk_count: int
