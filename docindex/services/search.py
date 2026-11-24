"""Semantic search over every stored chunk."""

from docindex.domain import DEFAULT_TOP_K, SearchResult
from docindex.embedding import Embedder
from docindex.storage import ChunkRepository


class SearchService:
    """Finds the stored chunks most similar to a natural-language query."""

    def __init__(self, embedder: Embedder, repository: ChunkRepository, top_k: int = DEFAULT_TOP_K) -> None:
        self._embedder = embedder
        self._repository = repository
        self._top_k = top_k

    @property
    def top_k(self) -> int:
        """The maximum number of search results returned."""
        return self._top_k

    def search(self, query: str) -> list[SearchResult]:
        """Return up to `top_k` search results, best first; empty when nothing is indexed."""
        self._repository.ensure_schema()
        return self._repository.search(self._embedder.embed_query(query), self._top_k)
