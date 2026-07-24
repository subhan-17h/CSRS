"""Offline tests for sparse BM25 retrieval."""

import json
import math
from pathlib import Path

import pytest

from csrs import retrieval as retrieval_module
from csrs.config import settings
from csrs.models import Chunk, RetrievedChunk, content_hash
from csrs.retrieval import (
    BM25Index,
    BM25IndexCorruptError,
    BM25IndexNotFoundError,
    _tokenize,
    compute_chunk_signature,
    hybrid_search,
    rerank,
    retrieve,
)
from csrs.store import ChunkStore


def make_chunk(
    chunk_id: str,
    text: str,
    section: str | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        text=text,
        doc_name="standard.txt",
        section=section,
        content_hash=content_hash(text),
    )


def test_tokenizer_keeps_control_ids_distinct() -> None:
    tokens = _tokenize(["AC-2 ACCOUNT MANAGEMENT", "AC-3 ACCOUNT MANAGEMENT"])

    assert tokens[0] == ["ac-2", "account", "manag"]
    assert tokens[1] == ["ac-3", "account", "manag"]
    assert tokens[0][0] != tokens[1][0]


def test_exact_control_id_ranks_matching_section_first() -> None:
    chunks = [
        make_chunk(
            "a-ac-3",
            "The organization enforces approved logical access.",
            "NIST SP 800-53 > AC-3 ACCESS ENFORCEMENT",
        ),
        make_chunk(
            "z-ac-2",
            "The organization manages information system accounts.",
            "NIST SP 800-53 > AC-2 ACCOUNT MANAGEMENT",
        ),
        make_chunk(
            "access-overview",
            "Access control policies govern account permissions.",
        ),
        make_chunk(
            "access-review",
            "Review access control assignments regularly.",
        ),
    ]

    results = BM25Index.build(chunks).search("AC-2", k=4)

    assert results[0][0] == "z-ac-2"


def test_search_respects_k_sorts_scores_and_omits_no_overlap() -> None:
    index = BM25Index.build(
        [
            make_chunk("accounts", "access account account management"),
            make_chunk("policy", "access control policy"),
            make_chunk("network", "network encryption guidance"),
        ]
    )

    results = index.search("access account", k=2)

    assert len(results) == 2
    assert [score for _, score in results] == sorted(
        (score for _, score in results), reverse=True
    )
    assert index.search("quasar nebula", k=3) == []
    assert index.search("the and", k=3) == []


def test_search_breaks_score_ties_by_chunk_id() -> None:
    index = BM25Index.build(
        [
            make_chunk("chunk-b", "identical access guidance"),
            make_chunk("chunk-a", "identical access guidance"),
        ]
    )

    assert [chunk_id for chunk_id, _ in index.search("access", k=2)] == [
        "chunk-a",
        "chunk-b",
    ]


def test_save_load_round_trip_preserves_results_and_signature(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bm25"
    BM25Index.build(
        [make_chunk("stale", "superseded network guidance")]
    ).save(path)
    index = BM25Index.build(
        [
            make_chunk("ac-2", "account management access control"),
            make_chunk("ia-2", "identification and authentication"),
        ]
    )

    index.save(path)
    loaded = BM25Index.load(path)

    assert loaded.search("account management", k=2) == index.search(
        "account management", k=2
    )
    assert loaded.search("superseded", k=2) == []
    assert loaded.signature == index.signature


def test_signature_changes_with_chunk_id_sequence() -> None:
    first = make_chunk("first", "first text")
    second = make_chunk("second", "second text")
    changed = second.model_copy(update={"id": "changed"})
    base_signature = compute_chunk_signature([first, second])

    assert compute_chunk_signature([first, second, changed]) != base_signature
    assert compute_chunk_signature([first]) != base_signature
    assert compute_chunk_signature([first, changed]) != base_signature


def test_signature_changes_when_content_changes_with_same_id_and_count() -> None:
    original = make_chunk("stable-id", "original account management guidance")
    changed = make_chunk("stable-id", "updated account management guidance")

    assert original.id == changed.id
    assert compute_chunk_signature([original]) != compute_chunk_signature([changed])


def test_load_distinguishes_missing_and_corrupt_directories(
    tmp_path: Path,
) -> None:
    with pytest.raises(BM25IndexNotFoundError, match="does not exist"):
        BM25Index.load(tmp_path / "missing")

    corrupt_path = tmp_path / "corrupt"
    corrupt_path.mkdir()
    (corrupt_path / "metadata.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(BM25IndexCorruptError, match="metadata is invalid"):
        BM25Index.load(corrupt_path)

    legacy_path = tmp_path / "legacy"
    BM25Index.build([]).save(legacy_path)
    metadata_path = legacy_path / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["format_version"] = 1
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(BM25IndexCorruptError, match="metadata is inconsistent"):
        BM25Index.load(legacy_path)


def test_empty_corpus_searches_and_round_trips_as_empty(tmp_path: Path) -> None:
    index = BM25Index.build([])
    path = tmp_path / "bm25"

    assert index.search("AC-2", k=5) == []
    assert index.signature == compute_chunk_signature([])

    index.save(path)
    loaded = BM25Index.load(path)

    assert loaded.search("AC-2", k=5) == []
    assert loaded.signature == index.signature


def test_chunks_with_embeddings_returns_existing_ids_as_plain_floats(
    tmp_path: Path,
) -> None:
    store = ChunkStore(path=tmp_path / "chroma")
    first = make_chunk("first", "First guidance")
    second = make_chunk("second", "Second guidance")
    store.add_chunks([first, second], [[1, 0], [0, 1]])

    stored = store.chunks_with_embeddings(["second", "missing", "first"])

    assert stored["first"] == (first, [1.0, 0.0])
    assert stored["second"] == (second, [0.0, 1.0])
    assert "missing" not in stored
    assert all(
        type(value) is float
        for _, embedding in stored.values()
        for value in embedding
    )


def test_hybrid_search_keeps_dense_and_sparse_only_chunks_with_cosine_scores(
    tmp_path: Path,
) -> None:
    store = ChunkStore(path=tmp_path / "chroma")
    dense_chunk = make_chunk("a-dense", "General access guidance")
    sparse_chunk = make_chunk("b-sparse", "Quasar authentication requirements")
    store.add_chunks([dense_chunk, sparse_chunk], [[1.0, 0.0], [1.0, 1.0]])
    sparse = BM25Index.build([dense_chunk, sparse_chunk])
    dense_result = store.search([1.0, 0.0], k=1)[0]

    results = hybrid_search(
        "quasar",
        [1.0, 0.0],
        store,
        sparse,
        limit=2,
        top_k_dense=1,
        top_k_bm25=1,
        rrf_k=60,
    )

    assert [result.chunk.id for result in results] == ["a-dense", "b-sparse"]
    assert [result.rank for result in results] == [0, 1]
    assert all(result.rrf_score is not None for result in results)
    assert results[0].score == dense_result.score
    assert results[1].score == pytest.approx(1.0 / math.sqrt(2.0))

    limited = hybrid_search(
        "quasar",
        [1.0, 0.0],
        store,
        sparse,
        limit=1,
        top_k_dense=1,
        top_k_bm25=1,
        rrf_k=60,
    )
    assert len(limited) == 1
    assert limited[0].rank == 0


def test_hybrid_search_scores_zero_norm_sparse_embedding_as_zero(
    tmp_path: Path,
) -> None:
    store = ChunkStore(path=tmp_path / "chroma")
    dense_chunk = make_chunk("a-dense", "General access guidance")
    zero_chunk = make_chunk("b-zero", "Nebula authentication requirements")
    store.add_chunks([dense_chunk, zero_chunk], [[1.0, 0.0], [0.0, 0.0]])

    results = hybrid_search(
        "nebula",
        [1.0, 0.0],
        store,
        BM25Index.build([dense_chunk, zero_chunk]),
        limit=2,
        top_k_dense=1,
        top_k_bm25=1,
        rrf_k=60,
    )

    zero_result = next(result for result in results if result.chunk.id == "b-zero")
    assert zero_result.score == 0.0
    assert zero_result.rrf_score is not None


def test_hybrid_search_returns_empty_for_empty_store_and_sparse_index(
    tmp_path: Path,
) -> None:
    store = ChunkStore(path=tmp_path / "chroma")

    assert hybrid_search(
        "anything",
        [1.0, 0.0],
        store,
        BM25Index.build([]),
        limit=5,
        top_k_dense=20,
        top_k_bm25=20,
        rrf_k=60,
    ) == []


def test_rerank_returns_empty_without_constructing_ranker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_ranker(model: str, cache_dir: Path) -> object:
        raise AssertionError("empty candidates must not construct a Ranker")

    monkeypatch.setattr(retrieval_module, "_ranker", fail_ranker)

    assert rerank(
        "anything",
        [],
        limit=5,
        model="fake-model",
        cache_dir=tmp_path,
    ) == []


def test_ranker_is_cached_by_model_and_cache_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    constructions: list[tuple[str, str, str]] = []

    class FakeRanker:
        def __init__(self, model_name: str, cache_dir: str, log_level: str) -> None:
            constructions.append((model_name, cache_dir, log_level))

    retrieval_module._ranker.cache_clear()
    monkeypatch.setattr(retrieval_module, "Ranker", FakeRanker)

    first = retrieval_module._ranker("model-a", tmp_path)
    second = retrieval_module._ranker("model-a", tmp_path)
    other = retrieval_module._ranker("model-b", tmp_path)

    assert first is second
    assert other is not first
    assert constructions == [
        ("model-a", str(tmp_path), "WARNING"),
        ("model-b", str(tmp_path), "WARNING"),
    ]
    retrieval_module._ranker.cache_clear()


def test_retrieve_reranks_full_dense_candidate_pool_without_touching_sparse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    candidates = [
        RetrievedChunk(
            chunk=make_chunk(f"chunk-{index}", f"Passage {index}"),
            score=1.0 - index / 100,
            rank=index,
        )
        for index in range(45)
    ]
    observed: dict[str, object] = {}

    class FakeStore:
        def search(
            self,
            query_embedding: list[float],
            k: int,
        ) -> list[RetrievedChunk]:
            observed["search"] = (query_embedding, k)
            return candidates[:k]

    class FailSparse:
        def search(self, question: str, k: int) -> list[tuple[str, float]]:
            raise AssertionError("dense retrieval must not consult the sparse index")

    class FakeRanker:
        def rerank(self, request: object) -> list[dict[str, object]]:
            observed["question"] = request.query
            observed["texts"] = [
                passage["text"] for passage in request.passages
            ]
            return [
                {**passage, "score": 1.0 - index / 100}
                for index, passage in enumerate(reversed(request.passages))
            ]

    monkeypatch.setattr(
        retrieval_module,
        "_ranker",
        lambda model, cache_dir: FakeRanker(),
    )

    results = retrieve(
        "Which passage is relevant?",
        [1.0, 0.0],
        FakeStore(),
        FailSparse(),
        limit=5,
        mode="dense",
        rerank_enabled=True,
        top_k_dense=20,
        top_k_bm25=20,
        rrf_k=60,
        rerank_candidates=40,
        flashrank_model="fake-model",
        flashrank_cache_dir=tmp_path,
    )

    assert observed["search"] == ([1.0, 0.0], 40)
    assert len(observed["texts"]) == 40
    assert [result.chunk.id for result in results] == [
        "chunk-39",
        "chunk-38",
        "chunk-37",
        "chunk-36",
        "chunk-35",
    ]
    assert [result.rank for result in results] == [0, 1, 2, 3, 4]
    assert [result.score for result in results] == [
        candidates[index].score for index in (39, 38, 37, 36, 35)
    ]
    assert [result.rerank_score for result in results] == [
        1.0,
        0.99,
        0.98,
        0.97,
        0.96,
    ]
    assert all(
        result.chunk is candidates[index].chunk
        for result, index in zip(results, (39, 38, 37, 36, 35), strict=True)
    )


def test_retrieve_sizes_hybrid_pool_before_reranking(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}
    sparse = BM25Index.build([])
    store = object()

    def fake_hybrid_search(
        question: str,
        query_embedding: list[float],
        store: object,
        sparse_index: BM25Index,
        *,
        limit: int,
        top_k_dense: int,
        top_k_bm25: int,
        rrf_k: int,
    ) -> list[RetrievedChunk]:
        observed["hybrid"] = (
            question,
            query_embedding,
            store,
            sparse_index,
            limit,
            top_k_dense,
            top_k_bm25,
            rrf_k,
        )
        return []

    monkeypatch.setattr(retrieval_module, "hybrid_search", fake_hybrid_search)

    results = retrieve(
        "question",
        [0.0, 1.0],
        store,
        sparse,
        limit=20,
        mode="hybrid",
        rerank_enabled=True,
        top_k_dense=20,
        top_k_bm25=20,
        rrf_k=60,
        rerank_candidates=40,
        flashrank_model="fake-model",
        flashrank_cache_dir=tmp_path,
    )

    assert results == []
    assert observed["hybrid"] == (
        "question",
        [0.0, 1.0],
        store,
        sparse,
        40,
        20,
        20,
        60,
    )


@pytest.mark.flashrank
def test_real_flashrank_prioritizes_obviously_relevant_passage() -> None:
    relevant = RetrievedChunk(
        chunk=make_chunk("relevant", "Paris is the capital city of France."),
        score=0.4,
    )
    candidates = [
        RetrievedChunk(
            chunk=make_chunk("irrelevant-1", "Bananas grow in warm tropical climates."),
            score=0.9,
        ),
        relevant,
        RetrievedChunk(
            chunk=make_chunk("irrelevant-2", "Whales are large marine mammals."),
            score=0.8,
        ),
    ]

    results = rerank(
        "What is the capital of France?",
        candidates,
        limit=3,
        model=settings.flashrank_model,
        cache_dir=settings.flashrank_cache_dir,
    )

    assert results[0].chunk.id == "relevant"
    assert results[0].rerank_score is not None
