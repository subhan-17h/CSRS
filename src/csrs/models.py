"""Shared data contracts for values exchanged between CSRS modules.

These types are the contract between every module. Values move through the pipeline as
Document -> Chunk -> RetrievedChunk -> Answer, with each stage adding what the next needs.
"""

import hashlib
from pathlib import Path

from pydantic import BaseModel


def content_hash(text: str) -> str:
    """Return the stable digest used to detect unchanged chunk content during indexing."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Chunk(BaseModel):
    """A persisted slice of a Document, ready for indexing and retrieval."""

    id: str
    text: str
    doc_name: str
    # These fields exist from day one but remain None until later tasks populate them:
    # T-2.1 adds PDF page numbers, T-2.2 adds control IDs and section breadcrumbs, and
    # T-3.6 adds parent_id for parent-child retrieval. Retrofitting a schema after chunks
    # are persisted in a vector store is far more painful than carrying None for a week.
    section: str | None = None
    page: int | None = None
    control_id: str | None = None
    parent_id: str | None = None
    content_hash: str

    @property
    def embed_text(self) -> str:
        """Return text enriched with its section breadcrumb for embedding."""
        return f"{self.section}\n\n{self.text}" if self.section is not None else self.text


class Document(BaseModel):
    """A loaded source document that will be split into Chunks."""

    name: str
    path: Path
    text: str
    page_count: int | None = None
    # Index 0 is page 1; TXT leaves this None, and T-2.2 maps chunk offsets onto it.
    pages: list[str] | None = None


class RetrievedChunk(BaseModel):
    """A Chunk paired with its retrieval score and optional final rank."""

    chunk: Chunk
    # Chroma's cosine distance is converted at the store boundary with 1.0 - distance.
    score: float
    rank: int | None = None
    rrf_score: float | None = None


class Answer(BaseModel):
    """The pipeline result, including response text and supporting RetrievedChunks."""

    text: str
    sources: list[RetrievedChunk]
    refused: bool = False
    model: str
    question: str
