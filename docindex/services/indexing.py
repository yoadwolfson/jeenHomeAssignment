"""The indexing run: extract, chunk, embed, store."""

import logging
from pathlib import Path

from docindex.chunking import ChunkerFactory
from docindex.domain import ChunkRecord, IndexingReport, SplitStrategy
from docindex.embedding import Embedder
from docindex.extraction import TextExtractor
from docindex.storage import ChunkRepository

logger = logging.getLogger(__name__)


class IndexingService:
    """Indexes one document with one split strategy, replacing its earlier chunks."""

    def __init__(
        self,
        extractor: TextExtractor,
        chunkers: ChunkerFactory,
        embedder: Embedder,
        repository: ChunkRepository,
    ) -> None:
        self._extractor = extractor
        self._chunkers = chunkers
        self._embedder = embedder
        self._repository = repository

    def index(self, path: Path, strategy: SplitStrategy) -> IndexingReport:
        """Run one indexing run for `path` and report how many chunks were stored."""
        clean_text = self._extractor.extract(path)
        logger.info("Extracted %d characters from %s", len(clean_text), path.name)
        chunks = self._chunkers.for_strategy(strategy).split(clean_text)
        logger.info("Split into %d chunks with strategy '%s'", len(chunks), strategy)
        # The database is checked before embedding so a stopped database costs no Gemini quota.
        self._repository.ensure_schema()
        embeddings = self._embedder.embed_documents(chunks)
        records = [
            ChunkRecord(path.name, strategy, chunk_index, text, embedding)
            for chunk_index, (text, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        self._repository.replace_chunks(path.name, strategy, records)
        return IndexingReport(path.name, strategy, len(records))
