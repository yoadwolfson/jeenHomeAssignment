"""Gemini client boundary: GeminiEmbedder against a fake genai.Client."""

import math
from dataclasses import dataclass, field
from typing import Any

from docindex.embedding.gemini import GeminiEmbedder

API_DIMENSIONS = 1536


@dataclass
class FakeEmbedding:
    values: list[float]


@dataclass
class FakeResponse:
    embeddings: list[FakeEmbedding]


@dataclass
class FakeModels:
    """Records each embed_content call and returns an unnormalised vector per text."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def embed_content(self, *, model: str, contents: list[str], config: Any) -> FakeResponse:
        self.calls.append({"model": model, "contents": list(contents), "config": config})
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
