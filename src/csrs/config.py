"""Centralised, typed configuration.

Every tunable in the system lives here. Phase 3 involves repeatedly adjusting chunk
sizes, `top_k` values and thresholds while watching the eval harness; hunting magic
numbers across modules would waste hours of that.

Values may be overridden from the environment or a `.env` file using the `CSRS_`
prefix, e.g. `CSRS_CHUNK_SIZE=512`. See `.env.example`.
"""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> csrs/ -> src/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All CSRS tunables, resolved once at import time."""

    model_config = SettingsConfigDict(
        env_prefix="CSRS_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Ollama -----------------------------------------------------------
    # Also honours the standard OLLAMA_HOST variable, since the ollama client
    # reads that itself and having the two disagree is a confusing failure.
    ollama_host: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("CSRS_OLLAMA_HOST", "OLLAMA_HOST"),
    )

    # Mandated by the spec. Never make this configurable away from nomic-embed-text
    # without also revisiting the search_document:/search_query: prefixes in
    # embeddings.py, which are specific to this model.
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768
    embed_batch_size: int = 32

    # Grading-facing default. llama3.2 (3B) follows grounding and refusal
    # instructions more reliably than the smaller models, which is the hard part
    # of T-1.6/T-4.2; the ~2 s it costs over qwen2.5:1.5b is worth that. All
    # supported models remain selectable in the UI.
    default_llm: str = "llama3.2"
    supported_llms: tuple[str, ...] = (
        "llama3.2",
        "qwen2.5:1.5b",
        "gemma2:2b",
        "phi4-mini",
        "gemma4:e2b",
    )

    # KV cache is allocated upfront, so this trades RAM for context headroom.
    num_ctx: int = 8192
    keep_alive: str = "30m"
    temperature: float = 0.1

    # --- Paths ------------------------------------------------------------
    docs_dir: Path = PROJECT_ROOT / "docs"
    chroma_dir: Path = PROJECT_ROOT / "chroma_db"
    bm25_dir: Path = PROJECT_ROOT / "bm25_index"
    manifest_path: Path = PROJECT_ROOT / "chroma_db" / "manifest.json"
    collection_name: str = "csrs"

    # --- PDF parsing ------------------------------------------------------
    pdf_parser: Literal["docling", "pypdf"] = "docling"
    docling_artifacts_path: Path = Path.home() / ".cache" / "docling" / "models"

    # --- Chunking ---------------------------------------------------------
    chunk_size: int = 400  # approximate tokens
    chunk_overlap: int = 60

    # --- Retrieval --------------------------------------------------------
    # Hybrid improved exact-ID ranking but regressed spec-example recall. T-3.5
    # revisits this default after reranking the fused candidate pool.
    retrieval_mode: Literal["dense", "hybrid"] = "dense"
    top_k_dense: int = 20
    top_k_bm25: int = 20
    rrf_k: int = 60
    rerank_top_n: int = 5

    # --- Generation -------------------------------------------------------
    # Placeholder default. T-4.2 calibrates this against the golden set's
    # out-of-scope questions; do not trust this number until it has.
    refusal_threshold: float = 0.3
    refusal_message: str = (
        "I could not find sufficient information in the loaded documents to answer that."
    )

    @model_validator(mode="after")
    def _check_chunking(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be smaller than "
                f"chunk_size ({self.chunk_size})"
            )
        return self


settings = Settings()
