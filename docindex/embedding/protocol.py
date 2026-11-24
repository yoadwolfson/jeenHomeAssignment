"""The Embedder protocol the services depend on."""

from typing import Protocol


class Embedder(Protocol):
    """Embeds chunk texts for storage and query texts for search."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one unit-length vector per text, in input order."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Return the unit-length vector for a search query."""
        ...
