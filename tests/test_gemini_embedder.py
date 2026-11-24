"""Gemini client boundary: GeminiEmbedder against a fake genai.Client."""

import math
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest
from google.genai import errors

from docindex.embedding.gemini import GeminiEmbedder, build_http_options
from docindex.errors import EmbeddingAuthError, EmbeddingError, EmbeddingQuotaError, EmbeddingServiceError

API_DIMENSIONS = 1536
SERVER_ERROR_CODE = 500
AUTH_MESSAGE = "Gemini rejected the API key: check GEMINI_API_KEY in .env"
QUOTA_WINDOW_SECONDS = 60.0


@dataclass
class FakeEmbedding:
    values: list[float]


@dataclass
class FakeResponse:
    embeddings: list[FakeEmbedding]


@dataclass
class FakeModels:
    """Records each embed_content call; raises `failure` or returns `response` if set, else one unnormalised vector per text."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    failure: Exception | None = None
    response: FakeResponse | None = None

    def embed_content(self, *, model: str, contents: list[str], config: Any) -> FakeResponse:
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        if self.failure is not None:
            raise self.failure
        if self.response is not None:
            return self.response
        # Encode the text's position in its first component so ordering is observable.
        return FakeResponse(
            [FakeEmbedding([float(int(text)) + 1.0] + [3.0] * (API_DIMENSIONS - 1)) for text in contents]
        )


@dataclass
class FakeClient:
    models: FakeModels = field(default_factory=FakeModels)


def numbered_texts(count: int) -> list[str]:
    return [str(position) for position in range(count)]


def test_documents_are_sent_in_batches_of_at_most_100_and_keep_their_order() -> None:
    client = FakeClient()
    embedder = GeminiEmbedder(client)

    vectors = embedder.embed_documents(numbered_texts(250))

    assert [len(call["contents"]) for call in client.models.calls] == [100, 100, 50]
    first_components = [vector[0] / vector[1] * 3.0 for vector in vectors]
    assert [round(component) for component in first_components] == [position + 1 for position in range(250)]


def test_documents_use_retrieval_document_and_queries_use_retrieval_query() -> None:
    client = FakeClient()
    embedder = GeminiEmbedder(client)

    embedder.embed_documents(numbered_texts(2))
    embedder.embed_query("7")

    document_call, query_call = client.models.calls
    assert document_call["model"] == "gemini-embedding-001"
    assert document_call["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert document_call["config"].output_dimensionality == 1536
    assert query_call["config"].task_type == "RETRIEVAL_QUERY"
    assert query_call["contents"] == ["7"]


def test_vectors_are_1536_dimensional_and_unit_length() -> None:
    embedder = GeminiEmbedder(FakeClient())

    vectors = embedder.embed_documents(numbered_texts(3)) + [embedder.embed_query("4")]

    for vector in vectors:
        assert len(vector) == 1536
        assert math.isclose(math.sqrt(sum(component * component for component in vector)), 1.0)


def test_no_call_is_made_for_an_empty_document_list() -> None:
    client = FakeClient()

    assert GeminiEmbedder(client).embed_documents([]) == []
    assert client.models.calls == []


def api_error(code: int, message: str = "error from Gemini", reason: str | None = None) -> errors.APIError:
    """An APIError of the subclass the SDK raises for `code`, with a Gemini-shaped error body."""
    details = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}] if reason else []
    body = {"error": {"code": code, "message": message, "status": "STATUS", "details": details}}
    error_class = errors.ServerError if code >= SERVER_ERROR_CODE else errors.ClientError
    return error_class(code, body, None)


def failure_raised_by(failure: Exception) -> EmbeddingError:
    """Embed one document through a client that raises `failure` and return what the embedder raised."""
    client = FakeClient()
    client.models.failure = failure
    with pytest.raises(EmbeddingError) as raised:
        GeminiEmbedder(client).embed_documents(["0"])
    return raised.value


@pytest.mark.parametrize(
    "failure",
    [
        api_error(401),
        api_error(403),
        api_error(400, "API key not valid. Please pass a valid API key.", reason="API_KEY_INVALID"),
    ],
    ids=["401", "403", "400-invalid-key"],
)
def test_a_rejected_api_key_raises_an_auth_error(failure: errors.APIError) -> None:
    raised = failure_raised_by(failure)

    assert isinstance(raised, EmbeddingAuthError)
    assert raised.message == AUTH_MESSAGE
    assert raised.__cause__ is failure


def test_a_rate_limit_still_failing_after_the_sdk_retries_raises_a_quota_error() -> None:
    failure = api_error(429, "Resource has been exhausted (e.g. check quota).")

    raised = failure_raised_by(failure)

    assert isinstance(raised, EmbeddingQuotaError)
    assert raised.message == "Gemini quota or rate limit exceeded after retries: wait and try again"
    assert raised.__cause__ is failure


@pytest.mark.parametrize("code", [500, 503, 400, 404])
def test_any_other_status_raises_a_service_error_naming_the_code(code: int) -> None:
    failure = api_error(code, "secret internal detail")

    raised = failure_raised_by(failure)

    assert isinstance(raised, EmbeddingServiceError)
    assert raised.message == f"Gemini embedding request failed: {code}"
    assert raised.__cause__ is failure


@pytest.mark.parametrize(
    "failure",
    [httpx2.ConnectError("[Errno 11001] getaddrinfo failed"), httpx2.ReadTimeout("The read operation timed out")],
    ids=["connect", "timeout"],
)
def test_a_network_failure_raises_a_service_error(failure: Exception) -> None:
    raised = failure_raised_by(failure)

    assert isinstance(raised, EmbeddingServiceError)
    assert raised.message == "Gemini embedding request failed: network error"
    assert raised.__cause__ is failure


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(None),  # type: ignore[arg-type]
        FakeResponse([FakeEmbedding([1.0] * API_DIMENSIONS)]),
        FakeResponse([FakeEmbedding([1.0] * API_DIMENSIONS), FakeEmbedding([])]),
        FakeResponse([FakeEmbedding([1.0] * API_DIMENSIONS), FakeEmbedding([1.0] * 768)]),
        FakeResponse([FakeEmbedding([1.0] * API_DIMENSIONS), FakeEmbedding([0.0] * API_DIMENSIONS)]),
    ],
    ids=["no-embeddings", "too-few", "empty-vector", "wrong-dimensions", "zero-vector"],
)
def test_an_unexpected_response_shape_raises_a_service_error(response: FakeResponse) -> None:
    client = FakeClient()
    client.models.response = response
    embedder = GeminiEmbedder(client)

    with pytest.raises(EmbeddingServiceError) as raised:
        embedder.embed_documents(["0", "1"])

    assert raised.value.message == "Gemini embedding request failed: unexpected response"


def test_the_client_retries_timeouts_rate_limits_and_server_errors() -> None:
    retry = build_http_options().retry_options

    assert retry is not None
    assert set(retry.http_status_codes or []) == {408, 429, 500, 502, 503, 504}


def test_the_retries_wait_long_enough_for_a_per_minute_quota_window_to_reset() -> None:
    retry = build_http_options().retry_options
    assert retry is not None and retry.attempts and retry.initial_delay and retry.max_delay

    # The SDK waits min(initial * 2**n, max) plus random jitter before retry n; jitter only adds time.
    shortest_total_wait = sum(
        min(retry.initial_delay * 2**retry_number, retry.max_delay) for retry_number in range(retry.attempts - 1)
    )

    assert shortest_total_wait >= QUOTA_WINDOW_SECONDS
