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


def test_document_names_include_indexed_empty_documents(store: ChunkStore) -> None:
    store.set_empty_document_names(["empty.txt"])

    assert store.empty_document_names() == ["empty.txt"]
    assert store.document_names() == ["empty.txt"]
    assert store._collection.configuration_json["hnsw"]["space"] == "cosine"


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
        "nested/second.txt": "second-hash",
        "first.txt": "first-hash",
    }

    save_manifest(manifest_path, manifest)

    assert load_manifest(manifest_path) == manifest
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
    assert list(manifest_path.parent.glob(".manifest.json.*.tmp")) == []


@pytest.mark.parametrize("content", ["garbage", "[]", '{"file.txt": 42}'])
def test_invalid_manifest_is_treated_as_empty(tmp_path: Path, content: str) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(content, encoding="utf-8")

    assert load_manifest(manifest_path) == {}
