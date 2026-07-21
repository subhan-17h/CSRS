"""Tests for the prefixed Ollama embedding boundary."""

from collections.abc import Sequence

import pytest

from csrs import embeddings
from csrs.config import settings


class FakeClient:
    def __init__(self, vector_width: int = 768) -> None:
        self.calls: list[tuple[str, str | list[str]]] = []
        self.vector_width = vector_width

    def embed(self, *, model: str, input: str | Sequence[str]) -> dict[str, list[list[float]]]:
        recorded_input = input if isinstance(input, str) else list(input)
        self.calls.append((model, recorded_input))
        count = 1 if isinstance(input, str) else len(input)
        return {"embeddings": [[0.0] * self.vector_width for _ in range(count)]}


def test_embed_documents_prepends_document_prefix_to_every_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr(embeddings, "_client", client)

    vectors = embeddings.embed_documents(["access control", "incident response"])

    assert len(vectors) == 2
    assert client.calls == [
        (
            settings.embed_model,
            ["search_document: access control", "search_document: incident response"],
        )
    ]


def test_embed_query_prepends_query_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(embeddings, "_client", client)

    vector = embeddings.embed_query("how should incidents be reported?")

    assert len(vector) == settings.embed_dim
    assert client.calls == [
        (settings.embed_model, "search_query: how should incidents be reported?")
    ]


def test_document_and_query_prefixes_are_different() -> None:
    assert embeddings._DOCUMENT_PREFIX != embeddings._QUERY_PREFIX


def test_document_batches_preserve_original_order(monkeypatch: pytest.MonkeyPatch) -> None:
    class OrderEncodingClient:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed(self, *, model: str, input: Sequence[str]) -> dict[str, list[list[float]]]:
            assert model == settings.embed_model
            batch = list(input)
            self.calls.append(batch)
            vectors = []
            for text in batch:
                source_index = int(text.removeprefix(embeddings._DOCUMENT_PREFIX))
                vectors.append([float(source_index), *([0.0] * (settings.embed_dim - 1))])
            return {"embeddings": vectors}

    client = OrderEncodingClient()
    monkeypatch.setattr(embeddings, "_client", client)
    texts = [str(index) for index in range(70)]

    vectors = embeddings.embed_documents(texts)

    assert [len(batch) for batch in client.calls] == [32, 32, 6]
    assert [text for batch in client.calls for text in batch] == [
        f"search_document: {text}" for text in texts
    ]
    assert [int(vector[0]) for vector in vectors] == list(range(70))


@pytest.mark.parametrize("embedding_kind", ["documents", "query"])
def test_wrong_width_vector_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch, embedding_kind: str
) -> None:
    monkeypatch.setattr(embeddings, "_client", FakeClient(vector_width=5))

    with pytest.raises(ValueError, match="Embedding dimension mismatch.*expected 768, got 5"):
        if embedding_kind == "documents":
            embeddings.embed_documents(["control"])
        else:
            embeddings.embed_query("control")
