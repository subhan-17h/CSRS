"""Offline tests for the public Pipeline facade."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from csrs import pipeline
from csrs.config import settings
from csrs.loaders.text import TextParser
from csrs.models import Answer, Document, RetrievedChunk
from csrs.store import load_manifest, save_manifest


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
    nested_dir = docs_dir / "nested"
    nested_dir.mkdir(parents=True)
    (nested_dir / "standard.txt").write_text(
        "Broken Access Control permits users to act outside their permissions.",
        encoding="utf-8",
    )

    result = offline_pipeline.index(docs_dir)

    assert result == pipeline.IndexResult(
        documents_indexed=1,
        chunks_created=1,
        added=1,
    )
    assert offline_pipeline.chunk_count() == result.chunks_created
    assert offline_pipeline.document_names() == ["standard.txt"]
    assert offline_pipeline.documents() == [
        pipeline.DocumentSummary(
            filename="standard.txt",
            chunk_count=1,
            page_count=None,
        )
    ]
    assert load_manifest(offline_pipeline._manifest_path) == {
        "nested/standard.txt": {
            "hash": pipeline.file_content_hash(nested_dir / "standard.txt"),
            "page_count": None,
            "chunk_count": 1,
        }
    }


def test_document_list_is_sorted_with_honest_txt_counts(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "second.txt").write_text("Access control guidance.", encoding="utf-8")
    (docs_dir / "first.txt").write_text("", encoding="utf-8")

    offline_pipeline.index(docs_dir)

    assert offline_pipeline.documents() == [
        pipeline.DocumentSummary("first.txt", chunk_count=0, page_count=None),
        pipeline.DocumentSummary("second.txt", chunk_count=1, page_count=None),
    ]


def test_document_list_persists_parser_page_count(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    source_path = docs_dir / "standard.pdf"
    source_path.write_bytes(b"stub pdf bytes")

    class StubPdfParser:
        def parse(self, path: Path) -> Document:
            return Document(
                name=path.name,
                path=path,
                text="Access control guidance.",
                page_count=3,
            )

    monkeypatch.setattr(pipeline, "get_parser", lambda path: StubPdfParser())

    offline_pipeline.index(docs_dir)

    assert offline_pipeline.documents() == [
        pipeline.DocumentSummary("standard.pdf", chunk_count=1, page_count=3)
    ]


def test_adding_document_appears_after_incremental_reindex(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "first.txt").write_text("First guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    (docs_dir / "second.txt").write_text("Second guidance.", encoding="utf-8")

    result = offline_pipeline.index(docs_dir)

    assert result == pipeline.IndexResult(
        documents_indexed=2,
        chunks_created=2,
        added=1,
        skipped=1,
    )
    assert offline_pipeline.documents() == [
        pipeline.DocumentSummary("first.txt", chunk_count=1, page_count=None),
        pipeline.DocumentSummary("second.txt", chunk_count=1, page_count=None),
    ]


def test_second_index_skips_unchanged_files_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")

    first = offline_pipeline.index(docs_dir)

    def fail_parse(self: TextParser, path: Path) -> Document:
        raise AssertionError(f"unchanged file must not be parsed: {path}")

    monkeypatch.setattr(TextParser, "parse", fail_parse)
    second = offline_pipeline.index(docs_dir)

    assert second == pipeline.IndexResult(
        documents_indexed=1,
        chunks_created=1,
        skipped=1,
    )
    assert offline_pipeline.chunk_count() == first.chunks_created
    assert offline_pipeline.document_names() == ["standard.txt"]


def test_index_reports_document_progress_for_parse_embed_skip_and_removal(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    source_path = docs_dir / "standard.txt"
    source_path.write_text("Access control guidance.", encoding="utf-8")
    progress: list[str] = []

    offline_pipeline.index(docs_dir, on_progress=progress.append)

    assert progress == [
        "Parsing document: standard.txt",
        "Embedding 1 chunk from standard.txt",
    ]

    progress.clear()
    offline_pipeline.index(docs_dir, on_progress=progress.append)
    assert progress == ["Skipped unchanged document: standard.txt"]

    progress.clear()
    source_path.unlink()
    offline_pipeline.index(docs_dir, on_progress=progress.append)
    assert progress == ["Removed document: standard.txt"]


def test_changing_one_files_content_reprocesses_only_that_file(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    first_path = docs_dir / "first.txt"
    second_path = docs_dir / "second.txt"
    first_path.write_text("First access control guidance.", encoding="utf-8")
    second_path.write_text("Second access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    parsed_paths: list[Path] = []
    original_parse = TextParser.parse

    def record_parse(self: TextParser, path: Path) -> Document:
        parsed_paths.append(path)
        return original_parse(self, path)

    monkeypatch.setattr(TextParser, "parse", record_parse)
    first_path.write_text("Changed access control guidance.", encoding="utf-8")

    result = offline_pipeline.index(docs_dir)

    assert result == pipeline.IndexResult(
        documents_indexed=2,
        chunks_created=2,
        updated=1,
        skipped=1,
    )
    assert parsed_paths == [first_path]


def test_rewriting_identical_content_stays_skipped(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    source_path = docs_dir / "standard.txt"
    content = "Access control guidance."
    source_path.write_text(content, encoding="utf-8")
    offline_pipeline.index(docs_dir)
    source_path.write_text(content, encoding="utf-8")

    def fail_parse(self: TextParser, path: Path) -> Document:
        raise AssertionError(f"identical file must not be parsed: {path}")

    monkeypatch.setattr(TextParser, "parse", fail_parse)

    result = offline_pipeline.index(docs_dir)

    assert result.skipped == 1
    assert result.updated == 0


def test_deleting_file_removes_chunks_and_manifest_entry(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    kept_path = docs_dir / "kept.txt"
    removed_path = docs_dir / "removed.txt"
    kept_path.write_text("Keep this guidance.", encoding="utf-8")
    removed_path.write_text("Remove this guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    removed_path.unlink()

    result = offline_pipeline.index(docs_dir)

    assert result == pipeline.IndexResult(
        documents_indexed=1,
        chunks_created=1,
        skipped=1,
        removed=1,
    )
    assert offline_pipeline.document_names() == ["kept.txt"]
    assert offline_pipeline.documents() == [
        pipeline.DocumentSummary("kept.txt", chunk_count=1, page_count=None)
    ]
    assert load_manifest(offline_pipeline._manifest_path) == {
        "kept.txt": {
            "hash": pipeline.file_content_hash(kept_path),
            "page_count": None,
            "chunk_count": 1,
        }
    }


def test_force_reprocesses_every_file(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    for name in ("first.txt", "second.txt"):
        (docs_dir / name).write_text(f"Guidance from {name}.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    parsed_paths: list[Path] = []
    original_parse = TextParser.parse

    def record_parse(self: TextParser, path: Path) -> Document:
        parsed_paths.append(path)
        return original_parse(self, path)

    monkeypatch.setattr(TextParser, "parse", record_parse)

    result = offline_pipeline.index(docs_dir, force=True)

    assert result == pipeline.IndexResult(
        documents_indexed=2,
        chunks_created=2,
        added=2,
    )
    assert parsed_paths == [docs_dir / "first.txt", docs_dir / "second.txt"]


@pytest.mark.parametrize("content", ["not json", '{"standard.txt": "old-hash"}'])
def test_invalid_manifest_rebuilds_without_raising(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
    content: str,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    offline_pipeline._manifest_path.write_text(content, encoding="utf-8")

    result = offline_pipeline.index(docs_dir)

    assert result.added == 1
    assert result.skipped == 0
    assert offline_pipeline.chunk_count() == 1


def test_empty_store_with_populated_manifest_rebuilds(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    assert load_manifest(offline_pipeline._manifest_path)
    offline_pipeline._store.reset()

    result = offline_pipeline.index(docs_dir)

    assert result.added == 1
    assert result.skipped == 0
    assert offline_pipeline.chunk_count() == 1


def test_partially_missing_store_rebuilds(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    for name in ("first.txt", "second.txt"):
        (docs_dir / name).write_text(f"Guidance from {name}.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    offline_pipeline._store.delete_document("first.txt")

    result = offline_pipeline.index(docs_dir)

    assert result == pipeline.IndexResult(
        documents_indexed=2,
        chunks_created=2,
        added=2,
    )
    assert offline_pipeline.document_names() == ["first.txt", "second.txt"]


def test_manifest_chunk_count_disagreement_rebuilds(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    manifest = load_manifest(offline_pipeline._manifest_path)
    manifest["standard.txt"]["chunk_count"] = 2
    save_manifest(offline_pipeline._manifest_path, manifest)

    result = offline_pipeline.index(docs_dir)

    assert result == pipeline.IndexResult(
        documents_indexed=1,
        chunks_created=1,
        added=1,
    )
    assert offline_pipeline.documents() == [
        pipeline.DocumentSummary("standard.txt", chunk_count=1, page_count=None)
    ]


def test_unchanged_empty_document_is_skipped(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "empty.txt").write_text("", encoding="utf-8")
    first = offline_pipeline.index(docs_dir)

    second = offline_pipeline.index(docs_dir)

    assert first == pipeline.IndexResult(documents_indexed=1, chunks_created=0, added=1)
    assert second == pipeline.IndexResult(documents_indexed=1, chunks_created=0, skipped=1)
    assert offline_pipeline.document_names() == ["empty.txt"]


def test_duplicate_basenames_are_rejected_before_indexing(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    for directory in (docs_dir / "first", docs_dir / "second"):
        directory.mkdir(parents=True)
        (directory / "standard.txt").write_text("Guidance.", encoding="utf-8")

    with pytest.raises(ValueError, match="Document filenames must be unique"):
        offline_pipeline.index(docs_dir)

    assert offline_pipeline.chunk_count() == 0
    assert not offline_pipeline._manifest_path.exists()


def test_moving_file_between_directories_preserves_its_chunks(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    old_dir = docs_dir / "old"
    new_dir = docs_dir / "new"
    old_dir.mkdir(parents=True)
    source_path = old_dir / "standard.txt"
    source_path.write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    new_dir.mkdir()
    moved_path = source_path.rename(new_dir / source_path.name)

    result = offline_pipeline.index(docs_dir)

    assert result == pipeline.IndexResult(
        documents_indexed=1,
        chunks_created=1,
        added=1,
        removed=1,
    )
    assert offline_pipeline.document_names() == ["standard.txt"]
    assert set(load_manifest(offline_pipeline._manifest_path)) == {"new/standard.txt"}
    assert moved_path.exists()


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
        temperature: float | None = None,
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
        temperature: float | None = None,
    ) -> Answer:
        observed["generation"] = (question, list(chunks), model, temperature)
        return expected

    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.0, 1.0, 0.0])
    monkeypatch.setattr(offline_pipeline._store, "search", fake_search)
    monkeypatch.setattr(pipeline, "generate_answer", fake_generation)

    answer = offline_pipeline.ask(
        "What is access control?",
        k=7,
        model="gemma2:2b",
        temperature=0.8,
    )

    assert answer is expected
    assert observed == {
        "query_embedding": [0.0, 1.0, 0.0],
        "k": 7,
        "generation": ("What is access control?", [], "gemma2:2b", 0.8),
    }


def test_ask_uses_configured_defaults_for_k_model_and_temperature(
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
        model=settings.default_llm,
        question="What is access control?",
    )

    def fake_search(query_embedding: Sequence[float], k: int) -> list[RetrievedChunk]:
        observed["k"] = k
        return []

    def fake_generation(
        question: str,
        chunks: Sequence[RetrievedChunk],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Answer:
        observed["generation"] = (question, list(chunks), model, temperature)
        return expected

    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.0, 1.0, 0.0])
    monkeypatch.setattr(offline_pipeline._store, "search", fake_search)
    monkeypatch.setattr(pipeline, "generate_answer", fake_generation)

    answer = offline_pipeline.ask("What is access control?")

    assert answer is expected
    # Defaults to rerank_top_n, not top_k_dense: with no reranker every retrieved chunk
    # reaches the model, and k=20 fills 92.4% of num_ctx (measured at T-1.7).
    assert observed == {
        "k": settings.rerank_top_n,
        "generation": (
            "What is access control?",
            [],
            settings.default_llm,
            settings.temperature,
        ),
    }
    assert settings.rerank_top_n < settings.top_k_dense


def test_model_availability_normalizes_latest_and_preserves_supported_order(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "list_installed_models",
        lambda: [
            "phi4-mini:latest",
            "unsupported:latest",
            "nomic-embed-text:latest",
            "llama3.2:latest",
        ],
    )

    availability = offline_pipeline.model_availability()

    assert availability == pipeline.ModelAvailability(
        selectable_models=("llama3.2", "phi4-mini"),
        missing_models=("qwen2.5:1.5b", "gemma2:2b", "gemma4:e2b"),
        ollama_reachable=True,
    )


def test_model_availability_reports_all_supported_models_missing_when_none_installed(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
) -> None:
    monkeypatch.setattr(pipeline, "list_installed_models", lambda: [])

    availability = offline_pipeline.model_availability()

    assert availability == pipeline.ModelAvailability(
        selectable_models=(),
        missing_models=settings.supported_llms,
        ollama_reachable=True,
    )


def test_model_availability_reports_unreachable_without_raising(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
) -> None:
    def fail_list() -> list[str]:
        raise ConnectionError("Ollama is down")

    monkeypatch.setattr(pipeline, "list_installed_models", fail_list)

    availability = offline_pipeline.model_availability()

    assert availability == pipeline.ModelAvailability(
        selectable_models=(),
        missing_models=(),
        ollama_reachable=False,
    )
