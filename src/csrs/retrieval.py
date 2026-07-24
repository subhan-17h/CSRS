"""Sparse retrieval over persisted chunks."""

import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path

import bm25s
import Stemmer

from csrs.models import Chunk, RetrievedChunk
from csrs.store import ChunkStore

__all__ = (
    "BM25Index",
    "BM25IndexCorruptError",
    "BM25IndexError",
    "BM25IndexNotFoundError",
    "compute_chunk_signature",
    "hybrid_search",
    "rrf_fuse",
)

_FORMAT_VERSION = 2
_METADATA_NAME = "metadata.json"
_TOKEN_PATTERN = r"(?u)\b\w[\w-]*\b"
_STEMMER = Stemmer.Stemmer("english")


class BM25IndexError(RuntimeError):
    """Base error raised when a persisted BM25 index cannot be loaded."""


class BM25IndexNotFoundError(BM25IndexError):
    """Raised when no persisted BM25 index exists at the requested path."""


class BM25IndexCorruptError(BM25IndexError):
    """Raised when a persisted BM25 index is incomplete or invalid."""


def _tokenize(texts: str | Sequence[str]) -> list[list[str]]:
    """Tokenize corpus and query text with one shared retrieval configuration."""
    return bm25s.tokenize(
        texts,
        token_pattern=_TOKEN_PATTERN,
        stopwords="en",
        stemmer=_STEMMER,
        return_ids=False,
        show_progress=False,
    )


def _signature_for_chunks(chunk_keys: Sequence[tuple[str, str]]) -> str:
    payload = json.dumps(
        {"chunks": list(chunk_keys), "count": len(chunk_keys)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_chunk_signature(chunks: Sequence[Chunk]) -> str:
    """Return the persisted-index signature without building a BM25 index."""
    return _signature_for_chunks(
        [(chunk.id, chunk.content_hash) for chunk in chunks]
    )


def rrf_fuse(
    rankings: Sequence[Sequence[str]],
    k: int,
) -> list[tuple[str, float]]:
    """Fuse ID rankings using reciprocal rank only."""
    if k <= 0:
        raise ValueError("k must be greater than zero")

    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, chunk_id in enumerate(ranking, start=1):
            if chunk_id in seen:
                raise ValueError("a ranking must not contain duplicate IDs")
            seen.add(chunk_id)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda result: (-result[1], result[0]))


class BM25Index:
    """A persisted BM25 index aligned with an ordered sequence of chunk IDs."""

    def __init__(
        self,
        index: bm25s.BM25 | None,
        chunk_ids: Sequence[str],
        content_hashes: Sequence[str],
        signature: str,
    ) -> None:
        self._index = index
        self._chunk_ids = tuple(chunk_ids)
        self._content_hashes = tuple(content_hashes)
        self._signature = signature

    @classmethod
    def build(cls, chunks: Sequence[Chunk]) -> "BM25Index":
        """Build an in-memory index over each chunk's embedding text."""
        chunk_list = list(chunks)
        chunk_ids = [chunk.id for chunk in chunk_list]
        content_hashes = [chunk.content_hash for chunk in chunk_list]
        signature = compute_chunk_signature(chunk_list)
        tokenized = _tokenize([chunk.embed_text for chunk in chunk_list])
        if not tokenized or not any(tokenized):
            return cls(None, chunk_ids, content_hashes, signature)

        index = bm25s.BM25()
        index.index(tokenized, show_progress=False)
        return cls(index, chunk_ids, content_hashes, signature)

    def save(self, path: Path) -> None:
        """Persist the BM25 data and ordered chunk metadata."""
        path.mkdir(parents=True, exist_ok=True)
        if self._index is not None:
            self._index.save(path, show_progress=False)

        metadata = {
            "chunk_ids": list(self._chunk_ids),
            "content_hashes": list(self._content_hashes),
            "count": len(self._chunk_ids),
            "format_version": _FORMAT_VERSION,
            "has_index": self._index is not None,
            "signature": self._signature,
        }
        (path / _METADATA_NAME).write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        """Load a persisted index or raise a specific missing/corrupt error."""
        if not path.exists():
            raise BM25IndexNotFoundError(f"BM25 index does not exist: {path}")
        if not path.is_dir():
            raise BM25IndexCorruptError(f"BM25 index path is not a directory: {path}")

        try:
            metadata = json.loads((path / _METADATA_NAME).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BM25IndexCorruptError(f"BM25 index metadata is invalid: {path}") from exc

        if not isinstance(metadata, dict) or set(metadata) != {
            "chunk_ids",
            "content_hashes",
            "count",
            "format_version",
            "has_index",
            "signature",
        }:
            raise BM25IndexCorruptError(f"BM25 index metadata has an invalid shape: {path}")

        chunk_ids = metadata["chunk_ids"]
        content_hashes = metadata["content_hashes"]
        count = metadata["count"]
        has_index = metadata["has_index"]
        signature = metadata["signature"]
        if (
            type(metadata["format_version"]) is not int
            or metadata["format_version"] != _FORMAT_VERSION
            or not isinstance(chunk_ids, list)
            or any(not isinstance(chunk_id, str) for chunk_id in chunk_ids)
            or not isinstance(content_hashes, list)
            or any(
                not isinstance(content_hash, str)
                for content_hash in content_hashes
            )
            or type(count) is not int
            or count != len(chunk_ids)
            or count != len(content_hashes)
            or type(has_index) is not bool
            or not isinstance(signature, str)
            or signature
            != _signature_for_chunks(
                list(zip(chunk_ids, content_hashes, strict=True))
            )
        ):
            raise BM25IndexCorruptError(f"BM25 index metadata is inconsistent: {path}")

        if not has_index:
            return cls(None, chunk_ids, content_hashes, signature)

        try:
            index = bm25s.BM25.load(path)
            indexed_count = index.scores["num_docs"]
        except Exception as exc:
            raise BM25IndexCorruptError(f"BM25 index data is invalid: {path}") from exc
        if indexed_count != count:
            raise BM25IndexCorruptError(
                f"BM25 index data contains {indexed_count} documents, expected {count}: {path}"
            )
        return cls(index, chunk_ids, content_hashes, signature)

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        """Return positive-scoring chunk IDs in deterministic rank order."""
        if k <= 0:
            raise ValueError("k must be greater than zero")
        if self._index is None:
            return []

        query_tokens = _tokenize(query)[0]
        query_token_ids = self._index.get_tokens_ids(query_tokens)
        if not query_token_ids:
            return []

        scores = self._index.get_scores_from_ids(query_token_ids)
        results = [
            (chunk_id, float(score))
            for chunk_id, score in zip(self._chunk_ids, scores, strict=True)
            if score > 0
        ]
        results.sort(key=lambda result: (-result[1], result[0]))
        return results[:k]

    @property
    def signature(self) -> str:
        """Return the stable digest of indexed chunk IDs, content hashes, and count."""
        return self._signature


def _cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def hybrid_search(
    question: str,
    query_embedding: Sequence[float],
    store: ChunkStore,
    sparse: BM25Index,
    *,
    limit: int,
    top_k_dense: int,
    top_k_bm25: int,
    rrf_k: int,
) -> list[RetrievedChunk]:
    """Fuse dense and sparse rankings while preserving dense cosine scores."""
    dense_results = store.search(query_embedding, top_k_dense)
    sparse_results = sparse.search(question, top_k_bm25)
    fused = rrf_fuse(
        [
            [result.chunk.id for result in dense_results],
            [chunk_id for chunk_id, _ in sparse_results],
        ],
        rrf_k,
    )[:limit]
    if not fused:
        return []

    dense_by_id = {result.chunk.id: result for result in dense_results}
    sparse_only_ids = [
        chunk_id for chunk_id, _ in fused if chunk_id not in dense_by_id
    ]
    stored_by_id = store.chunks_with_embeddings(sparse_only_ids)

    retrieved = []
    for chunk_id, rrf_score in fused:
        dense_result = dense_by_id.get(chunk_id)
        if dense_result is not None:
            chunk = dense_result.chunk
            score = dense_result.score
        else:
            stored = stored_by_id.get(chunk_id)
            if stored is None:
                continue
            chunk, embedding = stored
            score = _cosine_similarity(query_embedding, embedding)
        retrieved.append(
            RetrievedChunk(
                chunk=chunk,
                score=score,
                rank=len(retrieved),
                rrf_score=rrf_score,
            )
        )
    return retrieved
