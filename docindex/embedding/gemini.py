"""Embedder backed by the Gemini embedding API."""

import logging
import math

import httpx2
from google import genai
from google.genai import errors, types

from docindex.domain import EMBEDDING_DIMENSIONS
from docindex.errors import EmbeddingAuthError, EmbeddingError, EmbeddingQuotaError, EmbeddingServiceError

MODEL_NAME = "gemini-embedding-001"
# The API rejects batchEmbedContents requests holding more than 100 texts.
MAX_TEXTS_PER_REQUEST = 100
DOCUMENT_TASK_TYPE = "RETRIEVAL_DOCUMENT"
QUERY_TASK_TYPE = "RETRIEVAL_QUERY"
AUTH_STATUS_CODES = frozenset({401, 403})
BAD_REQUEST_STATUS_CODE = 400
RATE_LIMIT_STATUS_CODE = 429
# Gemini answers an invalid key with a plain 400 whose ErrorInfo carries this reason.
INVALID_KEY_REASON = "API_KEY_INVALID"
NETWORK_FAILURE_REASON = "network error"
UNEXPECTED_RESPONSE_REASON = "unexpected response"
# Free-tier quotas are per minute. Backoff waits 1, 2, 4 ... capped at 60 s, so 8 attempts
# wait at least 1+2+4+8+16+32+60 = 123 s in total: past a full window, even if the first 429 came right at its start.
RETRY_ATTEMPTS = 8
RETRY_INITIAL_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 60.0
REQUEST_TIMEOUT_STATUS_CODE = 408
# The transient 5xx codes; 501 Not Implemented and 505 would fail the same way again.
SERVER_ERROR_STATUS_CODES = (500, 502, 503, 504)
RETRYABLE_STATUS_CODES = (REQUEST_TIMEOUT_STATUS_CODE, RATE_LIMIT_STATUS_CODE, *SERVER_ERROR_STATUS_CODES)

logger = logging.getLogger(__name__)


def build_http_options() -> types.HttpOptions:
    """HTTP options that turn on the SDK's own exponential-backoff retry (it is off by default)."""
    return types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            attempts=RETRY_ATTEMPTS,
            initial_delay=RETRY_INITIAL_DELAY_SECONDS,
            max_delay=RETRY_MAX_DELAY_SECONDS,
            http_status_codes=list(RETRYABLE_STATUS_CODES),
        )
    )


def build_gemini_client(api_key: str) -> genai.Client:
    """Build a Gemini client that retries transient failures."""
    return genai.Client(api_key=api_key, http_options=build_http_options())


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
        response = self._request(texts, task_type)
        vectors = [embedding.values or [] for embedding in response.embeddings or []]
        if len(vectors) != len(texts) or any(not self._is_usable(vector) for vector in vectors):
            raise EmbeddingServiceError(UNEXPECTED_RESPONSE_REASON)
        return [_normalise(vector) for vector in vectors]

    def _request(self, texts: list[str], task_type: str) -> types.EmbedContentResponse:
        contents: list[types.ContentUnion] = list(texts)
        try:
            return self._client.models.embed_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self._dimensions),
            )
        except errors.APIError as error:
            raise _embedding_error_for(error) from error
        # The SDK's HTTP client is httpx2; its connection and timeout errors surface once the retries are used up.
        except httpx2.RequestError as error:
            raise EmbeddingServiceError(NETWORK_FAILURE_REASON) from error

    def _is_usable(self, vector: list[float]) -> bool:
        # A zero vector has no direction, so it cannot be normalised or compared.
        return len(vector) == self._dimensions and any(vector)


def _embedding_error_for(error: errors.APIError) -> EmbeddingError:
    """Translate an SDK error into ours, whose message never repeats the SDK's text."""
    if error.code in AUTH_STATUS_CODES or _is_invalid_key(error):
        return EmbeddingAuthError()
    if error.code == RATE_LIMIT_STATUS_CODE:
        return EmbeddingQuotaError()
    return EmbeddingServiceError(str(error.code))


def _is_invalid_key(error: errors.APIError) -> bool:
    if error.code != BAD_REQUEST_STATUS_CODE:
        return False
    body = error.details.get("error", {}) if isinstance(error.details, dict) else {}
    return any(detail.get("reason") == INVALID_KEY_REASON for detail in body.get("details", []))


def _normalise(vector: list[float]) -> list[float]:
    # gemini-embedding-001 only normalises its full 3072-dim output; truncated ones must be rescaled.
    norm = math.sqrt(sum(component * component for component in vector))
    return [component / norm for component in vector]
