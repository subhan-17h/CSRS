"""Offline tests for the public Pipeline facade."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from csrs import pipeline
from csrs.config import settings
from csrs.models import Answer, RetrievedChunk


def fake_document_embeddings(texts: Sequence[str]) -> list[list[float]]:
    return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
def offline_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pipeline.Pipeline:
    monkeypatch.setattr(pipeline, "embed_documents", fake_document_embeddings)
    return pipeline.Pipeline(chroma_path=tmp_path / "chroma")


def test_index_returns_counts_and_exposes_store_summary(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text(
        "Broken Access Control permits users to act outside their permissions.",
        encoding="utf-8",
    )

    result = offline_pipeline.index(docs_dir)

    assert result == pipeline.IndexResult(documents_indexed=1, chunks_created=1)
    assert offline_pipeline.chunk_count() == result.chunks_created
    assert offline_pipeline.document_names() == ["standard.txt"]


def test_index_twice_does_not_duplicate_chunks(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")

    first = offline_pipeline.index(docs_dir)
    second = offline_pipeline.index(docs_dir)

    assert first == second
    assert offline_pipeline.chunk_count() == first.chunks_created


def test_ask_on_empty_store_refuses_without_embedding_or_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = {"embedding": 0, "generation": 0}

    def fail_embedding(question: str) -> list[float]:
        calls["embedding"] += 1
        return [1.0, 0.0, 0.0]

    def fail_generation(
        question: str,
        chunks: Sequence[RetrievedChunk],
        model: str | None = None,
    ) -> Answer:
        calls["generation"] += 1
        raise AssertionError("generation must not run for an empty store")

    monkeypatch.setattr(pipeline, "embed_query", fail_embedding)
    monkeypatch.setattr(pipeline, "generate_answer", fail_generation)
    subject = pipeline.Pipeline(chroma_path=tmp_path / "empty-chroma")

    answer = subject.ask("What is the capital of France?")

    assert answer == Answer(
        text=settings.refusal_message,
        sources=[],
        refused=True,
        model=settings.default_llm,
        question="What is the capital of France?",
    )
    assert calls == {"embedding": 0, "generation": 0}


def test_ask_passes_caller_k_to_search_and_returns_answer_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    observed: dict[str, object] = {}
    expected = Answer(
        text="A grounded answer.",
        sources=[],
        model="gemma2:2b",
        question="What is access control?",
    )

    def fake_search(query_embedding: Sequence[float], k: int) -> list[RetrievedChunk]:
        observed["query_embedding"] = list(query_embedding)
        observed["k"] = k
        return []

    def fake_generation(
        question: str,
        chunks: Sequence[RetrievedChunk],
        model: str | None = None,
    ) -> Answer:
        observed["generation"] = (question, list(chunks), model)
        return expected

    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.0, 1.0, 0.0])
    monkeypatch.setattr(offline_pipeline._store, "search", fake_search)
    monkeypatch.setattr(pipeline, "generate_answer", fake_generation)

    answer = offline_pipeline.ask("What is access control?", k=7, model="gemma2:2b")

    assert answer is expected
    assert observed == {
        "query_embedding": [0.0, 1.0, 0.0],
        "k": 7,
        "generation": ("What is access control?", [], "gemma2:2b"),
    }
