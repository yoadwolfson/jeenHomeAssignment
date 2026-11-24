"""Embedder backed by the Gemini embedding API."""

import logging
import math

from google import genai
from google.genai import types

from docindex.domain import EMBEDDING_DIMENSIONS

MODEL_NAME = "gemini-embedding-001"
# The API rejects batchEmbedContents requests holding more than 100 texts.
MAX_TEXTS_PER_REQUEST = 100
DOCUMENT_TASK_TYPE = "RETRIEVAL_DOCUMENT"
QUERY_TASK_TYPE = "RETRIEVAL_QUERY"

logger = logging.getLogger(__name__)


class GeminiEmbedder:
    """Embeds texts with gemini-embedding-001 and L2-normalises the vectors."""

    def __init__(
        self,
        client: genai.Client,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = MAX_TEXTS_PER_REQUEST,
    ) -> None:
        self._client = client
        self._dimensions = dimensions
        self._batch_size = batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunk texts with RETRIEVAL_DOCUMENT, in batches, keeping input order."""
        batches = [texts[start : start + self._batch_size] for start in range(0, len(texts), self._batch_size)]
        vectors: list[list[float]] = []
        for batch_number, batch in enumerate(batches, start=1):
            logger.info("Embedding batch %d/%d (%d chunks)", batch_number, len(batches), len(batch))
            vectors.extend(self._embed(batch, DOCUMENT_TASK_TYPE))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query with RETRIEVAL_QUERY."""
        return self._embed([text], QUERY_TASK_TYPE)[0]

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        contents: list[types.ContentUnion] = list(texts)
        response = self._client.models.embed_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self._dimensions),
        )
        return [_normalise(embedding.values or []) for embedding in response.embeddings or []]


def _normalise(vector: list[float]) -> list[float]:
    # gemini-embedding-001 only normalises its full 3072-dim output; truncated ones must be rescaled.
    norm = math.sqrt(sum(component * component for component in vector))
    return [component / norm for component in vector]
