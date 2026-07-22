"""Tests for recursive and structure-aware text chunking."""

from pathlib import Path

import pytest

from csrs.chunking import CHARS_PER_TOKEN, _match_heading, chunk_document, split_text
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
    assert all(chunk.embed_text == chunk.text for chunk in first)


def test_pathological_inputs_terminate_without_empty_chunks() -> None:
    chunks = split_text("z" * 5_000, settings.chunk_size, settings.chunk_overlap)
    character_limit = settings.chunk_size * CHARS_PER_TOKEN

    assert chunks
    assert all(chunk and len(chunk) <= character_limit for chunk in chunks)
    assert split_text("", settings.chunk_size, settings.chunk_overlap) == []
    assert split_text(" \n\t \n", settings.chunk_size, settings.chunk_overlap) == []


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("### Access Policy", (6, "Access Policy", None)),
        ("## AC-2 ACCOUNT MANAGEMENT", (4, "AC-2 ACCOUNT MANAGEMENT", "AC-2")),
        ("AC-2 ACCOUNT MANAGEMENT", (4, "AC-2 ACCOUNT MANAGEMENT", "AC-2")),
        (
            "AC-2(1) AUTOMATED SYSTEM ACCOUNT MANAGEMENT",
            (5, "AC-2(1) AUTOMATED SYSTEM ACCOUNT MANAGEMENT", "AC-2(1)"),
        ),
        (
            "GV.RR-01: Organizational leadership",
            (5, "GV.RR-01", "GV.RR-01"),
        ),
        ("GV.RR: Category description", (4, "GV.RR", "GV.RR")),
        (
            "\u2022 Roles, Responsibilities, and Authorities (GV.RR): "
            "Cybersecurity roles, responsibilities, and authorities are established",
            (4, "GV.RR Roles, Responsibilities, and Authorities", "GV.RR"),
        ),
    ],
)
def test_heading_patterns_report_depth_label_and_control_id(
    line: str, expected: tuple[int, str, str | None]
) -> None:
    assert _match_heading(line) == expected


def test_toc_dot_leader_is_not_a_heading() -> None:
    toc_entry = "3.9 MAINTENANCE ......................................................... 162"

    assert _match_heading(toc_entry) is None
    assert _match_heading("3.9 MAINTENANCE") is None


def test_csf_parent_label_excludes_bullet_and_definition() -> None:
    heading = _match_heading(
        "\u2022 Roles, Responsibilities, and Authorities (GV.RR): "
        "Cybersecurity roles, responsibilities, and authorities are established"
    )

    assert heading == (4, "GV.RR Roles, Responsibilities, and Authorities", "GV.RR")
    assert heading is not None
    assert "\u2022" not in heading[1]
    assert "Cybersecurity roles" not in heading[1]


def test_csf_subcategory_label_is_control_id_only() -> None:
    heading = _match_heading(
        "o GV.RR-01: Organizational leadership is responsible and accountable for "
        "cybersecurity"
    )

    assert heading == (5, "GV.RR-01", "GV.RR-01")


def test_heading_label_is_truncated_to_80_characters() -> None:
    heading = _match_heading("# " + "A" * 100)

    assert heading == (6, "A" * 80, None)


def test_heading_stack_pushes_and_pops_on_dedent() -> None:
    document = _document(
        "AC-2 ACCOUNT MANAGEMENT\n"
        "Account requirements.\n"
        "AC-2(1) AUTOMATED SYSTEM ACCOUNT MANAGEMENT\n"
        "Enhancement requirements.\n"
        "AC-3 ACCESS ENFORCEMENT\n"
        "Access enforcement requirements."
    )

    chunks = chunk_document(document)
    account = next(chunk for chunk in chunks if "Account requirements." in chunk.text)
    enhancement = next(chunk for chunk in chunks if "Enhancement requirements." in chunk.text)
    access_enforcement = next(
        chunk for chunk in chunks if "Access enforcement requirements." in chunk.text
    )

    assert account.section == "standard.txt > AC-2 ACCOUNT MANAGEMENT"
    assert enhancement.section == (
        "standard.txt > AC-2 ACCOUNT MANAGEMENT > AC-2(1) AUTOMATED SYSTEM ACCOUNT MANAGEMENT"
    )
    assert access_enforcement.section == "standard.txt > AC-3 ACCESS ENFORCEMENT"
    assert access_enforcement.control_id == "AC-3"


def test_markdown_enhancement_inherits_nearest_control_id() -> None:
    document = _document(
        "## AC-2 ACCOUNT MANAGEMENT\n"
        "Control requirements.\n"
        "## (1) ACCOUNT MANAGEMENT | AUTOMATED SYSTEM ACCOUNT MANAGEMENT\n"
        "Enhancement requirements."
    )

    enhancement = next(
        chunk for chunk in chunk_document(document) if "Enhancement requirements." in chunk.text
    )

    assert enhancement.control_id == "AC-2(1)"
    assert enhancement.section == (
        "standard.txt > AC-2 ACCOUNT MANAGEMENT > "
        "(1) ACCOUNT MANAGEMENT | AUTOMATED SYSTEM ACCOUNT MANAGEMENT"
    )


def test_markdown_field_label_preserves_control_context() -> None:
    document = _document(
        "## AC-2 ACCOUNT MANAGEMENT\n"
        "## Control:\n"
        "Define account requirements."
    )

    chunk = next(
        chunk for chunk in chunk_document(document) if "Define account requirements." in chunk.text
    )

    assert _match_heading("## Control:") is None
    assert chunk.control_id == "AC-2"
    assert chunk.section == "standard.txt > AC-2 ACCOUNT MANAGEMENT"
    assert chunk.section is not None
    assert not chunk.section.endswith("Control:")


def test_non_markdown_csf_line_preserves_control_id() -> None:
    heading = _match_heading("GV.OC-01: The organizational context is understood.")

    assert heading == (5, "GV.OC-01", "GV.OC-01")


def test_breadcrumb_is_embedded_but_not_stored_in_raw_text() -> None:
    document = _document("AC-2 ACCOUNT MANAGEMENT\nDefine account requirements.")

    chunk = chunk_document(document)[0]

    assert chunk.section == "standard.txt > AC-2 ACCOUNT MANAGEMENT"
    assert chunk.embed_text.startswith(f"{chunk.section}\n\n")
    assert chunk.section not in chunk.text
    assert chunk.text == "AC-2 ACCOUNT MANAGEMENT\nDefine account requirements."


def test_control_and_page_metadata_come_from_explicit_pages() -> None:
    pages = [
        "AC-2 ACCOUNT MANAGEMENT\nDefine account requirements.",
        "Continued account requirements.\nAC-3 ACCESS ENFORCEMENT\nEnforce access.",
    ]
    document = Document(
        name="NIST.SP.800-53r5.pdf",
        path=Path("NIST.SP.800-53r5.pdf"),
        text="\n\n".join(pages),
        page_count=2,
        pages=pages,
    )

    chunks = chunk_document(document)
    continued = next(chunk for chunk in chunks if "Continued account" in chunk.text)
    access_enforcement = next(chunk for chunk in chunks if "Enforce access." in chunk.text)

    assert continued.page == 2
    assert continued.control_id == "AC-2"
    assert continued.section == "NIST.SP.800-53r5.pdf > AC-2 ACCOUNT MANAGEMENT"
    assert access_enforcement.page == 2
    assert access_enforcement.control_id == "AC-3"


def test_oversized_control_uses_bounded_recursive_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "chunk_size", 25)
    monkeypatch.setattr(settings, "chunk_overlap", 5)
    document = _document("AC-2 ACCOUNT MANAGEMENT\n" + "Requirement sentence. " * 20)

    chunks = chunk_document(document)
    character_limit = settings.chunk_size * CHARS_PER_TOKEN

    assert len(chunks) > 1
    assert all(len(chunk.text) <= character_limit for chunk in chunks)
    assert all(chunk.control_id == "AC-2" for chunk in chunks)
    assert all(chunk.section == "standard.txt > AC-2 ACCOUNT MANAGEMENT" for chunk in chunks)
