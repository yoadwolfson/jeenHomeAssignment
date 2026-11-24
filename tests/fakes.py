"""In-memory stand-ins for the Embedder and ChunkRepository protocols."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from docindex.domain import ChunkRecord, SearchResult, SplitStrategy

FAKE_DIMENSIONS = 8


def bag_of_letters_vector(text: str) -> list[float]:
    """A deterministic unit vector so related texts score higher than unrelated ones."""
    counts = [0.0] * FAKE_DIMENSIONS
    for character in text.lower():
        if character.isalpha():
            counts[ord(character) % FAKE_DIMENSIONS] += 1.0
    norm = math.sqrt(sum(count * count for count in counts)) or 1.0
    return [count / norm for count in counts]


@dataclass
class FakeEmbedder:
    """Embeds locally; `failure` is raised instead when set."""

    failure: BaseException | None = None
    embedded_texts: list[str] = field(default_factory=list)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        if self.failure is not None:
            raise self.failure
        self.embedded_texts.append(text)
        return bag_of_letters_vector(text)


@dataclass
class FakeChunkRepository:
    """Keeps chunk sets keyed by (filename, strategy), like the real table."""

    chunk_sets: dict[tuple[str, SplitStrategy], list[ChunkRecord]] = field(default_factory=dict)
    schema_ensured: bool = False

    def ensure_schema(self) -> None:
        self.schema_ensured = True

    def replace_chunks(self, filename: str, strategy: SplitStrategy, records: list[ChunkRecord]) -> None:
        self.chunk_sets[(filename, strategy)] = list(records)

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        scored = [
            SearchResult(record.filename, record.strategy, record.chunk_index, record.text, _dot(vector, record.embedding))
            for records in self.chunk_sets.values()
            for record in records
        ]
        return sorted(scored, key=lambda result: result.score, reverse=True)[:top_k]

    def records_for(self, filename: str, strategy: SplitStrategy) -> list[ChunkRecord]:
        return self.chunk_sets.get((filename, strategy), [])


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def constant(value: object) -> Callable[..., object]:
    """A builder that ignores its arguments and returns `value`."""
    return lambda *_args: value
