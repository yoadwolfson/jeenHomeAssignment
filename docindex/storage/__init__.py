"""Persisting chunks and searching them by similarity."""

from docindex.storage.postgres import PostgresChunkRepository
from docindex.storage.protocol import ChunkRepository

__all__ = ["ChunkRepository", "PostgresChunkRepository"]
