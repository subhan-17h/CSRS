"""Offline tests for the public Pipeline facade."""

import shutil
from collections.abc import Generator, Sequence
from pathlib import Path

import pytest

from csrs import pipeline
from csrs.config import settings
from csrs.loaders.text import TextParser
from csrs.models import Answer, Document, RetrievedChunk
from csrs.store import load_manifest, save_manifest


def fake_document_embeddings(texts: Sequence[str]) -> list[list[float]]:
    return [[1.0, 0.0, 0.0] for _ in texts]


def answer_stream(
    answer: Answer,
    tokens: Sequence[str] = (),
) -> Generator[str, None, Answer]:
    yield from tokens
    return answer


def consume_answer_stream(
    stream: Generator[str, None, Answer],
) -> tuple[list[str], Answer]:
    tokens = []
    while True:
        try:
            tokens.append(next(stream))
        except StopIteration as completed:
            return tokens, completed.value


@pytest.fixture
def offline_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pipeline.Pipeline:
    monkeypatch.setattr(pipeline, "embed_documents", fake_document_embeddings)
    return pipeline.Pipeline(chroma_path=tmp_path / "chroma")


def test_bm25_path_resolution_keeps_custom_chroma_isolated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configured_chroma = tmp_path / "configured-chroma"
    configured_bm25 = tmp_path / "configured-bm25"
    explicit_bm25 = tmp_path / "explicit-bm25"
    monkeypatch.setattr(settings, "chroma_dir", configured_chroma)
    monkeypatch.setattr(settings, "bm25_dir", configured_bm25)

    default_pipeline = pipeline.Pipeline()
    custom_pipeline = pipeline.Pipeline(chroma_path=tmp_path / "custom-chroma")
    explicit_pipeline = pipeline.Pipeline(
        chroma_path=tmp_path / "explicit-chroma",
        bm25_path=explicit_bm25,
    )

    assert default_pipeline._bm25_path == configured_bm25
    assert custom_pipeline._bm25_path == tmp_path / "custom-chroma" / "bm25_index"
    assert explicit_pipeline._bm25_path == explicit_bm25


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
        "Rebuilding the keyword index",
    ]

    progress.clear()
    offline_pipeline.index(docs_dir, on_progress=progress.append)
    assert progress == ["Skipped unchanged document: standard.txt"]

    progress.clear()
    source_path.unlink()
    offline_pipeline.index(docs_dir, on_progress=progress.append)
    assert progress == [
        "Removed document: standard.txt",
        "Rebuilding the keyword index",
    ]


def test_index_builds_searchable_bm25_under_custom_chroma_path(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text(
        "Quasar authentication prevents unauthorized access.",
        encoding="utf-8",
    )

    offline_pipeline.index(docs_dir)

    assert offline_pipeline._bm25_path == tmp_path / "chroma" / "bm25_index"
    assert offline_pipeline._bm25_path != settings.bm25_dir
    sparse_index = pipeline.BM25Index.load(offline_pipeline._bm25_path)
    standard_ids = {
        chunk.id
        for chunk in offline_pipeline._store.all_chunks()
        if chunk.doc_name == "standard.txt"
    }
    assert sparse_index.search("quasar authentication", k=1)[0][0] in standard_ids


def test_unchanged_reindex_does_not_rebuild_bm25(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text(
        "Access control guidance.",
        encoding="utf-8",
    )
    offline_pipeline.index(docs_dir)
    original_signature = pipeline.BM25Index.load(
        offline_pipeline._bm25_path
    ).signature
    original_build = pipeline.BM25Index.build
    build_calls = 0

    def record_build(chunks: Sequence[pipeline.Chunk]) -> pipeline.BM25Index:
        nonlocal build_calls
        build_calls += 1
        return original_build(chunks)

    monkeypatch.setattr(pipeline.BM25Index, "build", record_build)

    offline_pipeline.index(docs_dir)

    assert build_calls == 0
    assert (
        pipeline.BM25Index.load(offline_pipeline._bm25_path).signature
        == original_signature
    )


def test_adding_and_removing_documents_updates_bm25_signature(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "first.txt").write_text("First access guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    initial_signature = pipeline.BM25Index.load(
        offline_pipeline._bm25_path
    ).signature
    second_path = docs_dir / "second.txt"
    second_path.write_text("Second authentication guidance.", encoding="utf-8")

    offline_pipeline.index(docs_dir)

    added_signature = pipeline.BM25Index.load(
        offline_pipeline._bm25_path
    ).signature
    assert added_signature != initial_signature

    second_path.unlink()
    offline_pipeline.index(docs_dir)

    removed_signature = pipeline.BM25Index.load(
        offline_pipeline._bm25_path
    ).signature
    assert removed_signature != added_signature
    assert removed_signature == initial_signature


def test_sparse_index_builds_when_populated_store_has_no_persisted_index(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text(
        "Quasar authentication guidance.",
        encoding="utf-8",
    )
    offline_pipeline.index(docs_dir)
    shutil.rmtree(offline_pipeline._bm25_path)

    sparse_index = offline_pipeline.sparse_index()

    assert offline_pipeline._bm25_path.is_dir()
    assert sparse_index.search("quasar", k=1)


def test_sparse_index_rebuilds_stale_index_only_once(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text(
        "Quasar authentication guidance.",
        encoding="utf-8",
    )
    offline_pipeline.index(docs_dir)
    pipeline.BM25Index.build([]).save(offline_pipeline._bm25_path)
    stale_signature = pipeline.BM25Index.load(
        offline_pipeline._bm25_path
    ).signature
    original_build = pipeline.BM25Index.build
    build_calls = 0

    def record_build(chunks: Sequence[pipeline.Chunk]) -> pipeline.BM25Index:
        nonlocal build_calls
        build_calls += 1
        return original_build(chunks)

    monkeypatch.setattr(pipeline.BM25Index, "build", record_build)

    rebuilt_index = offline_pipeline.sparse_index()
    current_index = offline_pipeline.sparse_index()

    assert build_calls == 1
    assert rebuilt_index.signature != stale_signature
    assert current_index.signature == rebuilt_index.signature


def test_sparse_index_recovers_corrupt_directory(
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text(
        "Quasar authentication guidance.",
        encoding="utf-8",
    )
    offline_pipeline.index(docs_dir)
    (offline_pipeline._bm25_path / "metadata.json").write_text(
        "not json",
        encoding="utf-8",
    )

    sparse_index = offline_pipeline.sparse_index()

    assert sparse_index.search("quasar", k=1)
    assert (
        pipeline.BM25Index.load(offline_pipeline._bm25_path).signature
        == sparse_index.signature
    )


def test_sparse_index_handles_empty_store(
    tmp_path: Path,
) -> None:
    subject = pipeline.Pipeline(chroma_path=tmp_path / "empty-chroma")

    sparse_index = subject.sparse_index()

    assert sparse_index.search("anything", k=1) == []
    assert subject._bm25_path.is_dir()


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


def test_ask_routes_caller_k_through_retrieve_and_returns_answer_unchanged(
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
    sparse = pipeline.BM25Index.build([])

    def fake_retrieve(
        question: str,
        query_embedding: Sequence[float],
        store: object,
        sparse_index: pipeline.BM25Index,
        *,
        limit: int,
        mode: str,
        rerank_enabled: bool,
        top_k_dense: int,
        top_k_bm25: int,
        rrf_k: int,
        rerank_candidates: int,
        flashrank_model: str,
        flashrank_cache_dir: Path,
    ) -> list[RetrievedChunk]:
        observed["question"] = question
        observed["query_embedding"] = list(query_embedding)
        observed["store"] = store
        observed["sparse"] = sparse_index
        observed["retrieval"] = (
            limit,
            mode,
            rerank_enabled,
            top_k_dense,
            top_k_bm25,
            rrf_k,
            rerank_candidates,
            flashrank_model,
            flashrank_cache_dir,
        )
        return []

    def fake_generation(
        question: str,
        chunks: Sequence[RetrievedChunk],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Answer:
        observed["generation"] = (question, list(chunks), model, temperature)
        return expected

    def fake_embed(question: str) -> list[float]:
        observed["embedded_question"] = question
        return [0.0, 1.0, 0.0]

    monkeypatch.setattr(settings, "retrieval_mode", "hybrid")
    monkeypatch.setattr(pipeline, "embed_query", fake_embed)
    monkeypatch.setattr(offline_pipeline, "sparse_index", lambda: sparse)
    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    monkeypatch.setattr(pipeline, "generate_answer", fake_generation)

    answer = offline_pipeline.ask(
        "What is access control?",
        k=7,
        model="gemma2:2b",
        temperature=0.8,
    )

    assert answer == expected
    assert answer.rewritten_question is None
    assert observed == {
        "embedded_question": "What is access control?",
        "question": "What is access control?",
        "query_embedding": [0.0, 1.0, 0.0],
        "store": offline_pipeline._store,
        "sparse": sparse,
        "retrieval": (
            7,
            "hybrid",
            settings.rerank_enabled,
            settings.top_k_dense,
            settings.top_k_bm25,
            settings.rrf_k,
            settings.rerank_candidates,
            settings.flashrank_model,
            settings.flashrank_cache_dir,
        ),
        "generation": ("What is access control?", [], "gemma2:2b", 0.8),
    }


def test_ask_with_history_retrieves_rewrite_and_generates_original(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    original = "How is it implemented?"
    rewritten = "How is access control implemented?"
    history = [("What is access control?", "It restricts system access.")]
    observed: dict[str, object] = {}
    expected = Answer(
        text="A grounded answer.",
        sources=[],
        model=settings.default_llm,
        question=original,
    )

    def fake_retrieve(
        question: str,
        *args: object,
        **kwargs: object,
    ) -> list[RetrievedChunk]:
        observed["retrieved_question"] = question
        return []

    def fake_generation(
        question: str,
        chunks: Sequence[RetrievedChunk],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Answer:
        observed["generated_question"] = question
        return expected

    monkeypatch.setattr(settings, "retrieval_mode", "dense")
    monkeypatch.setattr(
        pipeline,
        "rewrite_query",
        lambda question, prior, model: rewritten,
    )
    monkeypatch.setattr(
        pipeline,
        "embed_query",
        lambda question: observed.setdefault("embedded_question", question) and [1.0],
    )
    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    monkeypatch.setattr(pipeline, "generate_answer", fake_generation)

    answer = offline_pipeline.ask(original, history=history)

    assert observed == {
        "embedded_question": rewritten,
        "retrieved_question": rewritten,
        "generated_question": original,
    }
    assert answer.rewritten_question == rewritten


def test_ask_and_ask_stream_share_retrieve_entry_point(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    calls: list[tuple[object, ...]] = []
    expected = Answer(
        text="A grounded answer.",
        sources=[],
        model=settings.default_llm,
        question="What is access control?",
    )

    def fake_retrieve(
        question: str,
        query_embedding: Sequence[float],
        store: object,
        sparse_index: pipeline.BM25Index | None,
        *,
        limit: int,
        mode: str,
        rerank_enabled: bool,
        top_k_dense: int,
        top_k_bm25: int,
        rrf_k: int,
        rerank_candidates: int,
        flashrank_model: str,
        flashrank_cache_dir: Path,
    ) -> list[RetrievedChunk]:
        calls.append(
            (
                question,
                list(query_embedding),
                store,
                sparse_index,
                limit,
                mode,
                rerank_enabled,
                top_k_dense,
                top_k_bm25,
                rrf_k,
                rerank_candidates,
                flashrank_model,
                flashrank_cache_dir,
            )
        )
        return []

    monkeypatch.setattr(settings, "retrieval_mode", "dense")
    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.0, 1.0, 0.0])
    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    monkeypatch.setattr(pipeline, "generate_answer", lambda *args: expected)
    monkeypatch.setattr(
        pipeline,
        "generate_answer_stream",
        lambda *args: answer_stream(expected),
    )

    answer = offline_pipeline.ask("What is access control?")
    stream = offline_pipeline.ask_stream("What is access control?")

    assert answer == expected
    assert consume_answer_stream(stream) == ([], expected)
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0] == (
        "What is access control?",
        [0.0, 1.0, 0.0],
        offline_pipeline._store,
        None,
        settings.rerank_top_n,
        "dense",
        settings.rerank_enabled,
        settings.top_k_dense,
        settings.top_k_bm25,
        settings.rrf_k,
        settings.rerank_candidates,
        settings.flashrank_model,
        settings.flashrank_cache_dir,
    )


@pytest.mark.parametrize(
    ("history", "search_query", "expected_rewrite"),
    [
        (None, "How is it implemented?", None),
        (
            [("What is access control?", "It restricts system access.")],
            "How is access control implemented?",
            "How is access control implemented?",
        ),
    ],
)
def test_ask_stream_uses_search_query_and_returns_rewrite(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
    history: Sequence[tuple[str, str]] | None,
    search_query: str,
    expected_rewrite: str | None,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    original = "How is it implemented?"
    observed: dict[str, object] = {}
    expected = Answer(
        text="A grounded answer.",
        sources=[],
        model=settings.default_llm,
        question=original,
    )

    def fake_retrieve(
        question: str,
        *args: object,
        **kwargs: object,
    ) -> list[RetrievedChunk]:
        observed["retrieved_question"] = question
        return []

    def fake_generation_stream(
        question: str,
        chunks: Sequence[RetrievedChunk],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Generator[str, None, Answer]:
        observed["generated_question"] = question
        return answer_stream(expected, ["Grounded answer."])

    monkeypatch.setattr(settings, "retrieval_mode", "dense")
    monkeypatch.setattr(
        pipeline,
        "rewrite_query",
        lambda question, prior, model: search_query,
    )
    monkeypatch.setattr(
        pipeline,
        "embed_query",
        lambda question: observed.setdefault("embedded_question", question) and [1.0],
    )
    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    monkeypatch.setattr(pipeline, "generate_answer_stream", fake_generation_stream)

    stream = offline_pipeline.ask_stream(original, history=history)
    tokens, answer = consume_answer_stream(stream)

    assert observed == {
        "embedded_question": search_query,
        "retrieved_question": search_query,
        "generated_question": original,
    }
    assert tokens == ["Grounded answer."]
    assert answer.rewritten_question == expected_rewrite


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

    monkeypatch.setattr(settings, "retrieval_mode", "dense")
    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.0, 1.0, 0.0])
    monkeypatch.setattr(offline_pipeline._store, "search", fake_search)
    monkeypatch.setattr(pipeline, "generate_answer", fake_generation)

    answer = offline_pipeline.ask("What is access control?")

    assert answer == expected
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


def test_ask_dense_mode_never_touches_sparse_retrieval(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    expected = Answer(
        text="A grounded answer.",
        sources=[],
        model=settings.default_llm,
        question="What is access control?",
    )
    searches: list[tuple[list[float], int]] = []

    def fail_sparse(*args: object, **kwargs: object) -> object:
        raise AssertionError("dense ask must not touch sparse retrieval")

    def fake_search(query_embedding: Sequence[float], k: int) -> list[RetrievedChunk]:
        searches.append((list(query_embedding), k))
        return []

    monkeypatch.setattr(settings, "retrieval_mode", "dense")
    monkeypatch.setattr(pipeline, "embed_query", lambda question: [0.0, 1.0, 0.0])
    monkeypatch.setattr(offline_pipeline._store, "search", fake_search)
    monkeypatch.setattr(offline_pipeline, "sparse_index", fail_sparse)
    monkeypatch.setattr(offline_pipeline._store, "all_chunks", fail_sparse)
    monkeypatch.setattr(pipeline.BM25Index, "load", fail_sparse)
    monkeypatch.setattr(pipeline, "generate_answer", lambda *args: expected)

    answer = offline_pipeline.ask("What is access control?")

    assert answer == expected
    assert searches == [([0.0, 1.0, 0.0], settings.rerank_top_n)]


def test_ask_reuses_cached_sparse_index_across_queries(
    monkeypatch: pytest.MonkeyPatch,
    offline_pipeline: pipeline.Pipeline,
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "standard.txt").write_text("Access control guidance.", encoding="utf-8")
    offline_pipeline.index(docs_dir)
    original_all_chunks = offline_pipeline._store.all_chunks
    scans = 0
    sparse_indexes: list[pipeline.BM25Index] = []

    def record_all_chunks() -> list[pipeline.Chunk]:
        nonlocal scans
        scans += 1
        return original_all_chunks()

    def fake_retrieve(
        question: str,
        query_embedding: Sequence[float],
        store: object,
        sparse_index: pipeline.BM25Index,
        *,
        limit: int,
        mode: str,
        rerank_enabled: bool,
        top_k_dense: int,
        top_k_bm25: int,
        rrf_k: int,
        rerank_candidates: int,
        flashrank_model: str,
        flashrank_cache_dir: Path,
    ) -> list[RetrievedChunk]:
        sparse_indexes.append(sparse_index)
        return []

    def fake_generation(
        question: str,
        chunks: Sequence[RetrievedChunk],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Answer:
        return Answer(text="Answer.", sources=[], model=model or "", question=question)

    monkeypatch.setattr(settings, "retrieval_mode", "hybrid")
    monkeypatch.setattr(offline_pipeline._store, "all_chunks", record_all_chunks)
    monkeypatch.setattr(pipeline, "embed_query", lambda question: [1.0, 0.0, 0.0])
    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    monkeypatch.setattr(pipeline, "generate_answer", fake_generation)

    offline_pipeline.ask("First question?")
    offline_pipeline.ask("Second question?")

    assert scans == 1
    assert len(sparse_indexes) == 2
    assert sparse_indexes[0] is sparse_indexes[1]


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
