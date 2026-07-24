"""Offline tests for the persistent Chroma chunk store."""

import json
import math
from pathlib import Path

import pytest

from csrs.models import Chunk
from csrs.store import ChunkStore, file_content_hash, load_manifest, save_manifest


def make_chunk(index: int) -> Chunk:
    return Chunk(
        id=f"chunk-{index}",
        text=f"Security guidance for topic {index}",
        doc_name="standard.txt",
        content_hash=f"hash-{index}",
    )


@pytest.fixture
def store(tmp_path: Path) -> ChunkStore:
    return ChunkStore(path=tmp_path / "chroma")


def test_related_chunk_ranks_first_with_cosine_scores(store: ChunkStore) -> None:
    chunks = [make_chunk(index) for index in range(10)]
    angles = [0.8, 1.1, 1.4, 1.7, 2.0, 2.3, 2.6, 0.0, 2.9, 0.4]
    vectors = [[math.cos(angle), math.sin(angle), 0.0] for angle in angles]

    store.add_chunks(chunks, vectors)
    results = store.search([1.0, 0.0, 0.0], k=10)
    raw = store._collection.query(
        query_embeddings=[[1.0, 0.0, 0.0]],
        n_results=10,
        include=["distances"],
    )

    assert results[0].chunk == chunks[7]
    assert [result.rank for result in results] == list(range(10))
    assert [result.score for result in results] == sorted(
        (result.score for result in results), reverse=True
    )
    assert [result.score for result in results] == pytest.approx(
        [1.0 - distance for distance in raw["distances"][0]]
    )


def test_collection_uses_cosine_space(store: ChunkStore) -> None:
    assert store._collection.configuration_json["hnsw"]["space"] == "cosine"


def test_chunk_with_none_metadata_round_trips_equal(store: ChunkStore) -> None:
    chunk = make_chunk(0)

    store.add_chunks([chunk], [[1.0, 0.0, 0.0]])

    assert store.search([1.0, 0.0, 0.0], k=1)[0].chunk == chunk


def test_all_chunks_returns_every_chunk_in_stable_id_order(
    store: ChunkStore,
) -> None:
    chunks = [make_chunk(index) for index in [2, 0, 1]]
    store.add_chunks(chunks, [[1.0, float(index)] for index in range(3)])

    expected = sorted(chunks, key=lambda chunk: chunk.id)

    assert store.all_chunks() == expected
    assert store.all_chunks() == expected


def test_all_chunks_round_trips_optional_metadata(store: ChunkStore) -> None:
    empty_metadata = make_chunk(0)
    full_metadata = make_chunk(1).model_copy(
        update={
            "section": "standard.txt > AC-2 ACCOUNT MANAGEMENT",
            "page": 17,
            "control_id": "AC-2",
            "parent_id": "standard.txt:parent:AC",
        }
    )
    store.add_chunks(
        [empty_metadata, full_metadata],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    assert store.all_chunks() == [empty_metadata, full_metadata]


def test_all_chunks_returns_empty_list_for_empty_store(store: ChunkStore) -> None:
    assert store.all_chunks() == []


def test_count_and_reset(store: ChunkStore) -> None:
    chunks = [make_chunk(0), make_chunk(1)]
    store.add_chunks(chunks, [[1.0, 0.0], [0.0, 1.0]])

    assert store.count() == 2

    store.reset()

    assert store.count() == 0
    assert store._collection.configuration_json["hnsw"]["space"] == "cosine"


def test_delete_document_removes_only_matching_chunks(store: ChunkStore) -> None:
    first = make_chunk(0)
    second = make_chunk(1).model_copy(
        update={"id": "other.txt:0", "doc_name": "other.txt"}
    )
    store.add_chunks([first, second], [[1.0, 0.0], [0.0, 1.0]])

    store.delete_document("standard.txt")

    assert store.count() == 1
    assert store.document_names() == ["other.txt"]


def test_document_chunk_counts_report_each_stored_document(store: ChunkStore) -> None:
    first = make_chunk(0)
    second = make_chunk(1)
    other = make_chunk(2).model_copy(
        update={"id": "other.txt:0", "doc_name": "other.txt"}
    )
    store.add_chunks(
        [first, second, other],
        [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
    )

    assert store.document_chunk_counts() == {"other.txt": 1, "standard.txt": 2}
    assert store.document_names() == ["other.txt", "standard.txt"]


def test_chunks_for_document_returns_chunks_in_numeric_id_order(
    store: ChunkStore,
) -> None:
    insertion_order = [10, 2, 11, 1, 0, 9, 3, 8, 4, 7, 5, 6]
    chunks = [
        Chunk(
            id=f"standard.txt:{index}",
            text=f"Chunk text {index}",
            doc_name="standard.txt",
            section=f"Section {index}",
            page=index + 1,
            control_id=f"AC-{index}",
            content_hash=f"hash-{index}",
        )
        for index in insertion_order
    ]
    store.add_chunks(
        chunks,
        [[float(index + 1), 1.0] for index in insertion_order],
    )

    page, total = store.chunks_for_document("standard.txt", limit=20, offset=0)

    assert total == 12
    assert page == sorted(chunks, key=lambda chunk: int(chunk.id.rsplit(":", 1)[1]))
    assert [chunk.id for chunk in page][2:11:8] == ["standard.txt:2", "standard.txt:10"]


def test_chunks_for_document_paginates_without_changing_total(
    store: ChunkStore,
) -> None:
    chunks = [
        Chunk(
            id=f"standard.txt:{index}",
            text=f"Chunk text {index}",
            doc_name="standard.txt",
            content_hash=f"hash-{index}",
        )
        for index in range(12)
    ]
    store.add_chunks(chunks, [[float(index + 1), 1.0] for index in range(12)])

    page, total = store.chunks_for_document("standard.txt", limit=2, offset=9)
    empty_page, empty_page_total = store.chunks_for_document(
        "standard.txt", limit=2, offset=20
    )
    unknown_page, unknown_total = store.chunks_for_document(
        "unknown.txt", limit=2, offset=0
    )

    assert [chunk.id for chunk in page] == ["standard.txt:9", "standard.txt:10"]
    assert total == 12
    assert empty_page == []
    assert empty_page_total == 12
    assert unknown_page == []
    assert unknown_total == 0


def test_chunks_for_document_keeps_malformed_ids_browseable(
    store: ChunkStore,
) -> None:
    valid = make_chunk(0).model_copy(update={"id": "standard.txt:0"})
    malformed = make_chunk(1).model_copy(update={"id": "standard.txt:not-a-number"})
    store.add_chunks([malformed, valid], [[0.0, 1.0], [1.0, 0.0]])

    page, total = store.chunks_for_document("standard.txt", limit=10, offset=0)

    assert [chunk.id for chunk in page] == [valid.id, malformed.id]
    assert total == 2


def test_file_content_hash_uses_bytes_not_metadata(tmp_path: Path) -> None:
    source_path = tmp_path / "standard.txt"
    source_path.write_bytes(b"same bytes")
    first_hash = file_content_hash(source_path)
    source_path.write_bytes(b"same bytes")

    assert file_content_hash(source_path) == first_hash

    source_path.write_bytes(b"changed bytes")

    assert file_content_hash(source_path) != first_hash


def test_manifest_round_trips_relative_paths_atomically(tmp_path: Path) -> None:
    manifest_path = tmp_path / "index" / "manifest.json"
    manifest = {
        "nested/second.pdf": {
            "hash": "second-hash",
            "page_count": 12,
            "chunk_count": 7,
        },
        "first.txt": {
            "hash": "first-hash",
            "page_count": None,
            "chunk_count": 1,
        },
    }

    save_manifest(manifest_path, manifest)

    assert load_manifest(manifest_path) == manifest
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
    assert list(manifest_path.parent.glob(".manifest.json.*.tmp")) == []


@pytest.mark.parametrize(
    "content",
    [
        "garbage",
        "[]",
        '{"file.txt": "old-format-hash"}',
        '{"file.txt": {"hash": "hash", "page_count": null}}',
        '{"file.txt": {"hash": "hash", "page_count": null, "chunk_count": true}}',
        (
            '{"file.txt": {"hash": "hash", "page_count": null, '
            '"chunk_count": 1, "extra": 2}}'
        ),
    ],
)
def test_invalid_manifest_is_treated_as_empty(tmp_path: Path, content: str) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(content, encoding="utf-8")

    assert load_manifest(manifest_path) == {}
