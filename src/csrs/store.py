"""Persistent Chroma storage for chunks and caller-supplied embeddings."""

from collections.abc import Sequence
from pathlib import Path

import chromadb

from csrs.config import settings
from csrs.models import Chunk, RetrievedChunk

__all__ = ("ChunkStore",)

_COSINE_METADATA = {"hnsw:space": "cosine"}


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

    def reset(self) -> None:
        """Delete every stored chunk by replacing the collection with a fresh one."""
        self._client.delete_collection(name=self._collection_name)
        self._collection = self._create_collection()
