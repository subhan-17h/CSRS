"""Ollama embedding boundary with the task prefixes required by Nomic Embed."""

from collections.abc import Sequence

import ollama

from csrs.config import settings

__all__ = ("embed_documents", "embed_query")

_DOCUMENT_PREFIX = "search_document: "
_QUERY_PREFIX = "search_query: "

_client = ollama.Client(host=settings.ollama_host)


def _validate_embeddings(
    vectors: Sequence[Sequence[float]], expected_count: int
) -> list[list[float]]:
    if len(vectors) != expected_count:
        raise ValueError(
            f"Embedding count mismatch: expected {expected_count}, got {len(vectors)}"
        )

    validated = []
    for position, vector in enumerate(vectors):
        if len(vector) != settings.embed_dim:
            raise ValueError(
                f"Embedding dimension mismatch at batch position {position}: "
                f"expected {settings.embed_dim}, got {len(vector)}"
            )
        validated.append(list(vector))
    return validated


def embed_documents(texts: Sequence[str]) -> list[list[float]]:
    """Embed indexed text with the document prefix, preserving input order."""
    prefixed_texts = [f"{_DOCUMENT_PREFIX}{text}" for text in texts]
    embeddings: list[list[float]] = []

    for start in range(0, len(prefixed_texts), settings.embed_batch_size):
        batch = prefixed_texts[start : start + settings.embed_batch_size]
        response = _client.embed(model=settings.embed_model, input=batch)
        embeddings.extend(_validate_embeddings(response["embeddings"], len(batch)))

    return embeddings


def embed_query(text: str) -> list[float]:
    """Embed search text with the query-specific task prefix."""
    response = _client.embed(model=settings.embed_model, input=f"{_QUERY_PREFIX}{text}")
    return _validate_embeddings(response["embeddings"], expected_count=1)[0]
