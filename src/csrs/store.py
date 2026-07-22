"""Persistent Chroma storage for chunks and caller-supplied embeddings."""

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypedDict

import chromadb

from csrs.config import settings
from csrs.models import Chunk, RetrievedChunk

__all__ = (
    "ChunkStore",
    "ManifestRecord",
    "file_content_hash",
    "load_manifest",
    "save_manifest",
)

_COSINE_METADATA = {"hnsw:space": "cosine"}
_HASH_BLOCK_SIZE = 1024 * 1024


class ManifestRecord(TypedDict):
    """Persisted source identity and exact indexed-document statistics."""

    hash: str
    page_count: int | None
    chunk_count: int


def file_content_hash(path: Path) -> str:
    """Return a SHA-256 digest of a file's bytes without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(_HASH_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, ManifestRecord]:
    """Load a document manifest, treating unreadable or invalid data as empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    for key, record in data.items():
        if (
            not isinstance(key, str)
            or not isinstance(record, dict)
            or set(record) != {"hash", "page_count", "chunk_count"}
            or not isinstance(record["hash"], str)
            or not (
                record["page_count"] is None
                or type(record["page_count"]) is int
                and record["page_count"] >= 0
            )
            or type(record["chunk_count"]) is not int
            or record["chunk_count"] < 0
        ):
            return {}
    return data


def save_manifest(path: Path, manifest: dict[str, ManifestRecord]) -> None:
    """Atomically replace the manifest with deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(manifest, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class ChunkStore:
    """Persist chunks and perform dense retrieval with zero-based result ranks."""

    def __init__(
        self,
        path: str | Path | None = None,
        collection_name: str | None = None,
    ) -> None:
        self._collection_name = collection_name or settings.collection_name
        self._client = chromadb.PersistentClient(path=str(path or settings.chroma_dir))
        self._collection = self._create_collection()

    def _create_collection(self):
        return self._client.get_or_create_collection(
            name=self._collection_name,
            metadata=_COSINE_METADATA,
        )

    def add_chunks(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Add chunks with explicit vectors, omitting metadata values Chroma rejects."""
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunk and embedding counts differ: {len(chunks)} != {len(embeddings)}"
            )
        if not chunks:
            return

        metadatas = []
        for chunk in chunks:
            metadata = {
                "doc_name": chunk.doc_name,
                "section": chunk.section,
                "page": chunk.page,
                "control_id": chunk.control_id,
                "parent_id": chunk.parent_id,
                "content_hash": chunk.content_hash,
            }
            metadatas.append({key: value for key, value in metadata.items() if value is not None})

        self._collection.add(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=metadatas,
            embeddings=[list(embedding) for embedding in embeddings],
        )

    def search(
        self,
        query_embedding: Sequence[float],
        k: int,
    ) -> list[RetrievedChunk]:
        """Return the nearest chunks with cosine similarity scores and zero-based ranks."""
        if k <= 0:
            raise ValueError("k must be greater than zero")
        if self.count() == 0:
            return []

        result = self._collection.query(
            query_embeddings=[list(query_embedding)],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        retrieved = []
        for rank, (chunk_id, text, metadata, distance) in enumerate(
            zip(ids, documents, metadatas, distances, strict=True)
        ):
            chunk = Chunk(
                id=chunk_id,
                text=text,
                doc_name=metadata["doc_name"],
                section=metadata.get("section"),
                page=metadata.get("page"),
                control_id=metadata.get("control_id"),
                parent_id=metadata.get("parent_id"),
                content_hash=metadata["content_hash"],
            )
            retrieved.append(
                RetrievedChunk(chunk=chunk, score=1.0 - distance, rank=rank)
            )
        return retrieved

    def chunks_for_document(
        self,
        doc_name: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Chunk], int]:
        """Return one numerically ordered page of chunks and the document total."""
        id_result = self._collection.get(
            where={"doc_name": doc_name},
            include=[],
        )
        ids = id_result["ids"]

        def chunk_order(chunk_id: str) -> tuple[int, int, str]:
            _, separator, suffix = chunk_id.rpartition(":")
            if separator:
                try:
                    return (0, int(suffix), chunk_id)
                except ValueError:
                    pass
            # Legacy or corrupt IDs stay browseable after every well-formed chunk.
            return (1, 0, chunk_id)

        ordered_ids = sorted(ids, key=chunk_order)
        page_ids = ordered_ids[offset : offset + limit]
        if not page_ids:
            return [], len(ordered_ids)

        page_result = self._collection.get(
            ids=page_ids,
            include=["documents", "metadatas"],
        )
        documents = page_result["documents"] or []
        metadatas = page_result["metadatas"] or []
        rows_by_id = {
            chunk_id: (text, metadata)
            for chunk_id, text, metadata in zip(
                page_result["ids"], documents, metadatas, strict=True
            )
        }

        chunks = []
        for chunk_id in page_ids:
            text, metadata = rows_by_id[chunk_id]
            chunks.append(
                Chunk(
                    id=chunk_id,
                    text=text,
                    doc_name=metadata["doc_name"],
                    section=metadata.get("section"),
                    page=metadata.get("page"),
                    control_id=metadata.get("control_id"),
                    parent_id=metadata.get("parent_id"),
                    content_hash=metadata["content_hash"],
                )
            )
        return chunks, len(ordered_ids)

    def count(self) -> int:
        """Return the number of chunks in the collection."""
        return self._collection.count()

    def delete_document(self, doc_name: str) -> None:
        """Delete every chunk whose metadata identifies the given document."""
        self._collection.delete(where={"doc_name": doc_name})

    def document_names(self) -> list[str]:
        """Return all distinct document names currently stored in the collection."""
        return sorted(self.document_chunk_counts())

    def document_chunk_counts(self) -> dict[str, int]:
        """Return exact chunk counts for documents represented in the collection."""
        result = self._collection.get(include=["metadatas"])
        metadatas = result["metadatas"] or []
        counts = Counter(metadata["doc_name"] for metadata in metadatas)
        return dict(sorted(counts.items()))

    def reset(self) -> None:
        """Delete every stored chunk by replacing the collection with a fresh one."""
        self._client.delete_collection(name=self._collection_name)
        self._collection = self._create_collection()
