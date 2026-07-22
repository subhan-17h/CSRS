"""Persistent Chroma storage for chunks and caller-supplied embeddings."""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile

import chromadb

from csrs.config import settings
from csrs.models import Chunk, RetrievedChunk

__all__ = (
    "ChunkStore",
    "file_content_hash",
    "load_manifest",
    "save_manifest",
)

_COSINE_METADATA = {"hnsw:space": "cosine"}
_EMPTY_DOCUMENTS_METADATA = "csrs:empty_documents"
_HASH_BLOCK_SIZE = 1024 * 1024


def file_content_hash(path: Path) -> str:
    """Return a SHA-256 digest of a file's bytes without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(_HASH_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, str]:
    """Load a path-to-hash manifest, treating unreadable or invalid data as empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        return {}
    return data


def save_manifest(path: Path, manifest: dict[str, str]) -> None:
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

    def count(self) -> int:
        """Return the number of chunks in the collection."""
        return self._collection.count()

    def delete_document(self, doc_name: str) -> None:
        """Delete every chunk whose metadata identifies the given document."""
        self._collection.delete(where={"doc_name": doc_name})

    def document_names(self) -> list[str]:
        """Return all distinct document names currently stored in the collection."""
        result = self._collection.get(include=["metadatas"])
        metadatas = result["metadatas"] or []
        names = {metadata["doc_name"] for metadata in metadatas}
        names.update(self.empty_document_names())
        return sorted(names)

    def empty_document_names(self) -> list[str]:
        """Return indexed document names that legitimately produced no chunks."""
        raw_names = (self._collection.metadata or {}).get(_EMPTY_DOCUMENTS_METADATA, "[]")
        try:
            names = json.loads(raw_names)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            return []
        return sorted(set(names))

    def set_empty_document_names(self, names: Sequence[str]) -> None:
        """Persist names for indexed documents that have no chunk metadata to inspect."""
        unique_names = sorted(set(names))
        if unique_names == self.empty_document_names():
            return
        metadata = dict(self._collection.metadata or {})
        metadata.pop("hnsw:space", None)
        metadata[_EMPTY_DOCUMENTS_METADATA] = json.dumps(unique_names)
        self._collection.modify(metadata=metadata)

    def reset(self) -> None:
        """Delete every stored chunk by replacing the collection with a fresh one."""
        self._client.delete_collection(name=self._collection_name)
        self._collection = self._create_collection()
