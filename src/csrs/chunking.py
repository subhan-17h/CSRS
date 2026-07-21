"""Recursive text chunking with deterministic, real-text overlap."""

import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass

from csrs.config import settings
from csrs.models import Chunk, Document, content_hash

CHARS_PER_TOKEN = 4
SEPARATORS = ["\n\n", "\n", ". ", " "]

Heading = tuple[int, str, str | None]
HeadingParser = Callable[[str, re.Match[str]], Heading]


def _markdown_heading(line: str, match: re.Match[str]) -> Heading:
    """Return metadata for a Markdown ATX heading."""
    return len(match.group(1)), match.group(2), None


def _numeric_heading(line: str, match: re.Match[str]) -> Heading:
    """Return metadata for a dotted numeric section heading."""
    return len(match.group(1).split(".")), match.group(2), None


def _control_heading(line: str, match: re.Match[str]) -> Heading:
    """Return metadata for a dashed control heading."""
    control_id = match.group(1)
    return 4, f"{control_id} {match.group(2)}", control_id


def _enhancement_heading(line: str, match: re.Match[str]) -> Heading:
    """Return metadata for a dashed control enhancement heading."""
    control_id = match.group(1)
    return 5, f"{control_id} {match.group(2)}", control_id


def _csf_heading(line: str, match: re.Match[str]) -> Heading:
    """Return metadata for a dotted CSF control or category heading."""
    control_id = match.group(1)
    depth = 5 if re.search(r"-\d+$", control_id) else 4
    return depth, control_id, control_id


def _csf_parent_heading(line: str, match: re.Match[str]) -> Heading:
    """Return metadata for a parenthesised CSF category heading."""
    control_id = match.group(2)
    return 4, f"{control_id} {match.group(1)}", control_id


_HEADING_PATTERNS: tuple[tuple[re.Pattern[str], HeadingParser], ...] = (
    (re.compile(r"^(#{1,6})\s+(.+)$"), _markdown_heading),
    (re.compile(r"^(\d+(?:\.\d+)+)\s+([A-Z].*)$"), _numeric_heading),
    (
        re.compile(r"^([A-Z]{2}-\d+\(\d+\))\s+([A-Z][A-Z0-9 ,\-()/]{3,})$"),
        _enhancement_heading,
    ),
    (
        re.compile(r"^([A-Z]{2}-\d+)\s+([A-Z][A-Z0-9 ,\-()/]{3,})$"),
        _control_heading,
    ),
    (re.compile(r"^[-o*\s]*([A-Z]{2}\.[A-Z]{2}(?:-\d+)?)\s*:"), _csf_heading),
    (
        re.compile(r"^\W*(.+?)\s+\(([A-Z]{2}\.[A-Z]{2})\)\s*:"),
        _csf_parent_heading,
    ),
)


@dataclass(frozen=True, slots=True)
class _Block:
    """A page-local text block paired with its structural context."""

    text: str
    headings: tuple[Heading, ...]
    control_id: str | None
    page: int | None


def _match_heading(line: str) -> Heading | None:
    """Return structural metadata for a heading line, if recognised."""
    if "...." in line:
        return None
    for pattern, parser in _HEADING_PATTERNS:
        if match := pattern.search(line):
            depth, label, control_id = parser(line, match)
            return depth, label[:80], control_id
    return None


def _nearest_control(headings: list[Heading]) -> str | None:
    """Return the nearest control identifier on a heading stack."""
    return next((control_id for _, _, control_id in reversed(headings) if control_id), None)


def _document_blocks(document: Document) -> list[_Block]:
    """Split a document into page-local blocks while tracking its heading stack."""
    pages = document.pages if document.pages is not None else [document.text]
    page_aware = document.pages is not None
    headings: list[Heading] = []
    blocks: list[_Block] = []

    for page_number, page_text in enumerate(pages, start=1):
        lines: list[str] = []
        snapshot = tuple(headings)
        control_id = _nearest_control(headings)
        page = page_number if page_aware else None

        for line in page_text.splitlines(keepends=True):
            heading = _match_heading(line.strip())
            if heading is None:
                lines.append(line)
                continue

            block_text = "".join(lines)
            if block_text.strip():
                blocks.append(_Block(block_text, snapshot, control_id, page))

            depth, _, _ = heading
            while headings and headings[-1][0] >= depth:
                headings.pop()
            headings.append(heading)
            lines = [line]
            snapshot = tuple(headings)
            control_id = _nearest_control(headings)

        block_text = "".join(lines)
        if block_text.strip():
            blocks.append(_Block(block_text, snapshot, control_id, page))

    return blocks


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
    """Split a document at structural boundaries and populate Chunk metadata."""
    character_limit = settings.chunk_size * CHARS_PER_TOKEN
    chunks: list[Chunk] = []

    for block in _document_blocks(document):
        texts = (
            [block.text]
            if len(block.text) <= character_limit
            else split_text(block.text, settings.chunk_size, settings.chunk_overlap)
        )
        section = (
            " > ".join([document.name, *(label for _, label, _ in block.headings)])
            if block.headings
            else None
        )
        for text in texts:
            chunks.append(
                Chunk(
                    id=f"{document.name}:{len(chunks)}",
                    text=text,
                    doc_name=document.name,
                    section=section,
                    page=block.page,
                    control_id=block.control_id,
                    content_hash=content_hash(text),
                )
            )

    return chunks
