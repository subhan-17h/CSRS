"""Recursive text chunking with deterministic, real-text overlap."""

from bisect import bisect_right

from csrs.config import settings
from csrs.models import Chunk, Document, content_hash

CHARS_PER_TOKEN = 4
SEPARATORS = ["\n\n", "\n", ". ", " "]


def _split_on_separator(text: str, separator: str) -> list[str]:
    """Split text without discarding the separator characters."""
    parts = text.split(separator)
    return [part + separator for part in parts[:-1]] + [parts[-1]]


def _recursive_split(text: str, limit: int, separators: list[str]) -> list[str]:
    """Return separator-aware pieces no longer than ``limit`` characters."""
    if len(text) <= limit:
        return [text]
    if not separators:
        return [text[start : start + limit] for start in range(0, len(text), limit)]

    separator, *remaining = separators
    if separator not in text:
        return _recursive_split(text, limit, remaining)

    pieces: list[str] = []
    for piece in _split_on_separator(text, separator):
        if len(piece) <= limit:
            pieces.append(piece)
        else:
            pieces.extend(_recursive_split(piece, limit, remaining))
    return pieces


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text using approximate token sizes and real overlapping text.

    ``chunk_size`` and ``overlap`` are token counts. Tokens are approximated using
    ``CHARS_PER_TOKEN`` so this pure function remains independent of model tokenizers.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must not be negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text or not text.strip():
        return []

    limit = chunk_size * CHARS_PER_TOKEN
    overlap_chars = overlap * CHARS_PER_TOKEN
    pieces = _recursive_split(text, limit, SEPARATORS)

    boundaries: list[int] = []
    position = 0
    for piece in pieces:
        position += len(piece)
        boundaries.append(position)

    chunks: list[str] = []
    start = 0
    while start < len(text):
        maximum_end = min(start + limit, len(text))
        boundary_index = bisect_right(boundaries, maximum_end) - 1
        end = boundaries[boundary_index] if boundary_index >= 0 else maximum_end

        # An overlap can put the next start inside a recursively split piece. If its
        # next boundary would not advance beyond that overlap, use a bounded hard cut.
        if end <= start + overlap_chars and maximum_end < len(text):
            end = maximum_end

        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap_chars

    return chunks


def chunk_document(document: Document) -> list[Chunk]:
    """Split a document and map its text slices to stable Chunk contracts."""
    texts = split_text(document.text, settings.chunk_size, settings.chunk_overlap)
    return [
        Chunk(
            id=f"{document.name}:{index}",
            text=text,
            doc_name=document.name,
            content_hash=content_hash(text),
        )
        for index, text in enumerate(texts)
    ]
