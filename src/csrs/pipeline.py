"""Public facade composing the CSRS indexing and question-answering pipeline."""

from collections import Counter
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path

from csrs.chunking import chunk_document
from csrs.config import settings
from csrs.embeddings import embed_documents, embed_query
from csrs.generation import (
    canonical_model_name,
    generate_answer,
    generate_answer_stream,
    list_installed_models,
)
from csrs.loaders import get_parser, iter_document_paths
from csrs.models import Answer, Chunk
from csrs.store import ChunkStore, file_content_hash, load_manifest, save_manifest

__all__ = ("DocumentSummary", "IndexResult", "ModelAvailability", "Pipeline")


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    """Persisted statistics for one indexed source document."""

    filename: str
    chunk_count: int
    page_count: int | None


@dataclass(frozen=True, slots=True)
class IndexResult:
    """Current index totals and activity counts from one indexing run."""

    documents_indexed: int
    chunks_created: int
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0


@dataclass(frozen=True, slots=True)
class ModelAvailability:
    """Supported model choices and the state of the Ollama connection."""

    selectable_models: tuple[str, ...]
    missing_models: tuple[str, ...]
    ollama_reachable: bool


class Pipeline:
    """Expose the complete CSRS workflow without leaking backend dependencies."""

    def __init__(
        self,
        chroma_path: str | Path | None = None,
        collection_name: str | None = None,
        manifest_path: str | Path | None = None,
    ) -> None:
        resolved_chroma_path = (
            Path(chroma_path) if chroma_path is not None else settings.chroma_dir
        )
        self._store = ChunkStore(
            path=resolved_chroma_path,
            collection_name=(
                collection_name if collection_name is not None else settings.collection_name
            ),
        )
        if manifest_path is not None:
            self._manifest_path = Path(manifest_path)
        elif chroma_path is not None:
            self._manifest_path = resolved_chroma_path / "manifest.json"
        else:
            self._manifest_path = settings.manifest_path

    def index(
        self,
        docs_dir: Path | None = None,
        *,
        force: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> IndexResult:
        """Incrementally index files whose source bytes changed."""
        source_dir = docs_dir if docs_dir is not None else settings.docs_dir
        paths_by_identity = {
            path.relative_to(source_dir).as_posix(): path
            for path in iter_document_paths(source_dir)
        }
        doc_names = [path.name for path in paths_by_identity.values()]
        duplicate_names = sorted(
            name for name, count in Counter(doc_names).items() if count > 1
        )
        if duplicate_names:
            joined_names = ", ".join(duplicate_names)
            raise ValueError(
                f"Document filenames must be unique across the docs directory: {joined_names}"
            )

        manifest = load_manifest(self._manifest_path)
        manifest_doc_names = [Path(identity).name for identity in manifest]
        manifest_names = set(manifest_doc_names)
        manifest_has_duplicate_names = len(manifest_doc_names) != len(manifest_names)
        expected_chunk_counts = {
            Path(identity).name: record["chunk_count"]
            for identity, record in manifest.items()
            if record["chunk_count"] > 0
        }
        if (
            force
            or manifest_has_duplicate_names
            or expected_chunk_counts != self._store.document_chunk_counts()
        ):
            self._store.reset()
            manifest = {}
        added = 0
        updated = 0
        skipped = 0
        removed = 0
        current_doc_names = set(doc_names)

        for identity, path in paths_by_identity.items():
            source_hash = file_content_hash(path)
            previous_record = manifest.get(identity)
            if previous_record is not None and previous_record["hash"] == source_hash:
                skipped += 1
                if on_progress is not None:
                    on_progress(f"Skipped unchanged document: {path.name}")
                continue

            parser = get_parser(path)
            if parser is None:
                continue
            if on_progress is not None:
                on_progress(f"Parsing document: {path.name}")
            document = parser.parse(path)
            chunks = chunk_document(document)
            if on_progress is not None:
                chunk_label = "chunk" if len(chunks) == 1 else "chunks"
                on_progress(f"Embedding {len(chunks)} {chunk_label} from {path.name}")
            embeddings = (
                embed_documents([chunk.embed_text for chunk in chunks]) if chunks else []
            )

            self._store.delete_document(document.name)
            self._store.add_chunks(chunks, embeddings)
            manifest[identity] = {
                "hash": source_hash,
                "page_count": document.page_count,
                "chunk_count": len(chunks),
            }
            if previous_record is None:
                added += 1
            else:
                updated += 1

        for identity in sorted(set(manifest) - set(paths_by_identity)):
            doc_name = Path(identity).name
            if doc_name not in current_doc_names:
                self._store.delete_document(doc_name)
            del manifest[identity]
            removed += 1
            if on_progress is not None:
                on_progress(f"Removed document: {doc_name}")

        save_manifest(self._manifest_path, manifest)

        return IndexResult(
            documents_indexed=len(manifest),
            chunks_created=self._store.count(),
            added=added,
            updated=updated,
            skipped=skipped,
            removed=removed,
        )

    def ask(
        self,
        question: str,
        k: int | None = None,
        model: str | None = None,
        temperature: float | None = None,
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

        # Everything retrieved goes straight to the model, because there is no reranker.
        # `top_k_dense` (20) is the retrieval *candidate pool*, not the generation context:
        # measured at T-1.7, k=20 fills 92.4% of `num_ctx` and Ollama truncates silently
        # rather than erroring. `rerank_top_n` already means "chunks that reach generation",
        # so default to it. When a reranker lands it narrows top_k_dense -> rerank_top_n
        # here, and this default stops being a stand-in.
        selected_k = k if k is not None else settings.rerank_top_n
        selected_temperature = (
            temperature if temperature is not None else settings.temperature
        )
        query_embedding = embed_query(question)
        chunks = self._store.search(query_embedding, selected_k)
        return generate_answer(
            question,
            chunks,
            selected_model,
            selected_temperature,
        )

    def ask_stream(
        self,
        question: str,
        k: int | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> Generator[str, None, Answer]:
        """Retrieve grounded context now and return its lazy answer token stream."""
        selected_model = model if model is not None else settings.default_llm
        if self._store.count() == 0:
            return generate_answer_stream(
                question,
                [],
                selected_model,
                temperature,
            )

        # Keep this retrieval path visibly identical to ask(); stage events depend on
        # retrieval finishing when this method returns, before generation is advanced.
        selected_k = k if k is not None else settings.rerank_top_n
        selected_temperature = (
            temperature if temperature is not None else settings.temperature
        )
        query_embedding = embed_query(question)
        chunks = self._store.search(query_embedding, selected_k)
        return generate_answer_stream(
            question,
            chunks,
            selected_model,
            selected_temperature,
        )

    def model_availability(self) -> ModelAvailability:
        """Return ordered model choices, missing models, and Ollama reachability.

        When Ollama is unreachable, both model tuples are empty because installed and
        missing state cannot be known. A reachable server with no installed supported
        models returns every supported model as missing instead.
        """
        try:
            installed = {
                canonical_model_name(name) for name in list_installed_models()
            }
        except ConnectionError:
            return ModelAvailability((), (), False)

        selectable = tuple(
            name
            for name in settings.supported_llms
            if canonical_model_name(name) in installed
        )
        missing = tuple(name for name in settings.supported_llms if name not in selectable)
        return ModelAvailability(selectable, missing, True)

    def document_names(self) -> list[str]:
        """Return document names from the complete persistent index."""
        return [document.filename for document in self.documents()]

    def documents(self) -> list[DocumentSummary]:
        """Return persisted document statistics sorted by filename."""
        manifest = load_manifest(self._manifest_path)
        return sorted(
            (
                DocumentSummary(
                    filename=Path(identity).name,
                    chunk_count=record["chunk_count"],
                    page_count=record["page_count"],
                )
                for identity, record in manifest.items()
            ),
            key=lambda document: document.filename,
        )

    def document_chunks(
        self,
        doc_name: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Chunk], int]:
        """Return one ordered page of chunks for an indexed document."""
        return self._store.chunks_for_document(doc_name, limit, offset)

    def chunk_count(self) -> int:
        """Return the number of chunks currently available for retrieval."""
        return self._store.count()
