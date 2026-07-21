"""Offline tests for the persistent Chroma chunk store."""

import math
from pathlib import Path

import pytest

from csrs.models import Chunk
from csrs.store import ChunkStore


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
