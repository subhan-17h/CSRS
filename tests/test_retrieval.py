"""Offline tests for sparse BM25 retrieval."""

import json
from pathlib import Path

import pytest

from csrs.models import Chunk, content_hash
from csrs.retrieval import (
    BM25Index,
    BM25IndexCorruptError,
    BM25IndexNotFoundError,
    _tokenize,
    compute_chunk_signature,
)


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
