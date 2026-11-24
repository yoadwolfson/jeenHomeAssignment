"""Composition root: the only place concrete classes are wired together."""

from collections.abc import Callable

from google import genai

from docindex.chunking import (
    ChunkerFactory,
    FixedSizeChunker,
    ParagraphChunker,
    PysbdSentenceSplitter,
    SentenceChunker,
)
from docindex.config import Settings
from docindex.domain import SplitStrategy
from docindex.embedding import Embedder
from docindex.embedding.gemini import GeminiEmbedder
from docindex.extraction import DocxExtractor, ExtractorRegistry, PdfExtractor, TextCleaner
from docindex.services import IndexingService, SearchService
from docindex.storage import ChunkRepository, PostgresChunkRepository

type EmbedderBuilder = Callable[[Settings], Embedder]
type RepositoryBuilder = Callable[[Settings], ChunkRepository]


def build_gemini_embedder(settings: Settings) -> Embedder:
    """Build the Gemini-backed embedder."""
    return GeminiEmbedder(genai.Client(api_key=settings.gemini_api_key))


def build_extractor_registry() -> ExtractorRegistry:
    """Build the registry of supported document formats, sharing one set of clean-text rules."""
    cleaner = TextCleaner()
    return ExtractorRegistry({".pdf": PdfExtractor(cleaner), ".docx": DocxExtractor(cleaner)})


def build_chunker_factory() -> ChunkerFactory:
    """Build the chunker for every split strategy, sharing one English sentence splitter."""
    splitter = PysbdSentenceSplitter()
    return ChunkerFactory(
        {
            SplitStrategy.fixed: FixedSizeChunker(),
            SplitStrategy.sentence: SentenceChunker(splitter),
            SplitStrategy.paragraph: ParagraphChunker(splitter),
        }
    )


def build_postgres_repository(settings: Settings) -> ChunkRepository:
    """Build the pgvector-backed chunk repository."""
    return PostgresChunkRepository(settings.postgres_url)


class ServiceFactory:
    """Builds the services from settings; the external adapters are swappable for tests."""

    def __init__(
        self,
        embedder_builder: EmbedderBuilder = build_gemini_embedder,
        repository_builder: RepositoryBuilder = build_postgres_repository,
    ) -> None:
        self._embedder_builder = embedder_builder
        self._repository_builder = repository_builder

    def build_indexing_service(self, settings: Settings) -> IndexingService:
        """Wire the indexing service for one run."""
        return IndexingService(
            extractor=build_extractor_registry(),
            chunkers=build_chunker_factory(),
            embedder=self._embedder_builder(settings),
            repository=self._repository_builder(settings),
        )

    def build_search_service(self, settings: Settings) -> SearchService:
        """Wire the search service."""
        return SearchService(self._embedder_builder(settings), self._repository_builder(settings))
