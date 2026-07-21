"""Public facade composing the CSRS indexing and question-answering pipeline."""

from dataclasses import dataclass
from pathlib import Path

from csrs.chunking import chunk_document
from csrs.config import settings
from csrs.embeddings import embed_documents, embed_query
from csrs.generation import generate_answer
from csrs.loaders import iter_documents
from csrs.models import Answer
from csrs.store import ChunkStore

__all__ = ("IndexResult", "Pipeline")


@dataclass(frozen=True, slots=True)
class IndexResult:
    """Counts produced by a completed full-corpus indexing run."""

    documents_indexed: int
    chunks_created: int


class Pipeline:
    """Expose the complete CSRS workflow without leaking backend dependencies."""

    def __init__(
        self,
        chroma_path: str | Path | None = None,
        collection_name: str | None = None,
    ) -> None:
        self._store = ChunkStore(
            path=chroma_path if chroma_path is not None else settings.chroma_dir,
            collection_name=(
                collection_name if collection_name is not None else settings.collection_name
            ),
        )
        self._document_names: list[str] = []

    def index(self, docs_dir: Path | None = None) -> IndexResult:
        """Load, chunk, embed, and replace the complete document index."""
        source_dir = docs_dir if docs_dir is not None else settings.docs_dir
        documents = list(iter_documents(source_dir))
        chunks = [chunk for document in documents for chunk in chunk_document(document)]
        embeddings = embed_documents([chunk.text for chunk in chunks])

        # T-2.3 replaces this full reset with content-hash incremental indexing.
        self._store.reset()
        self._store.add_chunks(chunks, embeddings)
        self._document_names = sorted({document.name for document in documents})

        return IndexResult(
            documents_indexed=len(documents),
            chunks_created=len(chunks),
        )

    def ask(
        self,
        question: str,
        k: int | None = None,
        model: str | None = None,
    ) -> Answer:
        """Retrieve grounded context and return the generated answer unchanged."""
        selected_model = model if model is not None else settings.default_llm
        if self._store.count() == 0:
            return Answer(
                text=settings.refusal_message,
                sources=[],
                refused=True,
                model=selected_model,
                question=question,
            )

        selected_k = k if k is not None else settings.top_k_dense
        query_embedding = embed_query(question)
        chunks = self._store.search(query_embedding, selected_k)
        return generate_answer(question, chunks, selected_model)

    def document_names(self) -> list[str]:
        """Return document names from the most recent indexing run."""
        return list(self._document_names)

    def chunk_count(self) -> int:
        """Return the number of chunks currently available for retrieval."""
        return self._store.count()
