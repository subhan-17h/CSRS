"""Tests for the naive recursive text chunker."""

from pathlib import Path

from csrs.chunking import CHARS_PER_TOKEN, chunk_document, split_text
from csrs.config import settings
from csrs.models import Document


def _document(text: str) -> Document:
    return Document(name="standard.txt", path=Path("standard.txt"), text=text)


def _ten_thousand_chars() -> str:
    paragraph = (
        "Organizations identify risks, select safeguards, verify controls, and record "
        "evidence for independent review. "
    )
    return (paragraph * 100)[:10_000]


def test_document_yields_sane_number_of_bounded_chunks() -> None:
    chunks = chunk_document(_document(_ten_thousand_chars()))
    character_limit = settings.chunk_size * CHARS_PER_TOKEN

    assert 8 <= len(chunks) <= 10
    assert all(0 < len(chunk.text) <= character_limit for chunk in chunks)


def test_consecutive_chunks_share_actual_text() -> None:
    chunks = split_text(_ten_thousand_chars(), settings.chunk_size, settings.chunk_overlap)
    overlap_chars = settings.chunk_overlap * CHARS_PER_TOKEN

    for previous, following in zip(chunks, chunks[1:], strict=False):
        assert previous[-overlap_chars:] == following[:overlap_chars]


def test_sentence_straddling_boundary_survives_in_next_chunk() -> None:
    sentence = "Boundary sentence survives whole."
    text = "x" * 84 + " " + sentence + " " + "y" * 100

    chunks = split_text(text, chunk_size=25, overlap=10)

    assert sentence not in chunks[0]
    assert sentence in chunks[1]


def test_chunk_metadata_is_deterministic() -> None:
    document = _document(_ten_thousand_chars())

    first = chunk_document(document)
    second = chunk_document(document)

    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert [chunk.content_hash for chunk in first] == [chunk.content_hash for chunk in second]
    assert all(chunk.doc_name == document.name for chunk in first)
    assert all(
        chunk.section is None
        and chunk.page is None
        and chunk.control_id is None
        and chunk.parent_id is None
        for chunk in first
    )


def test_pathological_inputs_terminate_without_empty_chunks() -> None:
    chunks = split_text("z" * 5_000, settings.chunk_size, settings.chunk_overlap)
    character_limit = settings.chunk_size * CHARS_PER_TOKEN

    assert chunks
    assert all(chunk and len(chunk) <= character_limit for chunk in chunks)
    assert split_text("", settings.chunk_size, settings.chunk_overlap) == []
    assert split_text(" \n\t \n", settings.chunk_size, settings.chunk_overlap) == []
