"""Tests for structural PDF parsing with Docling."""

from pathlib import Path

import pytest

from csrs.loaders import DoclingParser, PdfParser, get_parser
from csrs.loaders.docling_parser import _split_pages


def test_docling_parser_is_registered(monkeypatch) -> None:
    monkeypatch.setattr("csrs.loaders.settings.pdf_parser", "docling")
    assert isinstance(get_parser(Path("a.pdf")), DoclingParser)


def test_pypdf_parser_is_registered(monkeypatch) -> None:
    monkeypatch.setattr("csrs.loaders.settings.pdf_parser", "pypdf")
    assert isinstance(get_parser(Path("a.pdf")), PdfParser)


def test_split_pages_returns_exact_segments() -> None:
    placeholder = "<!-- page -->"
    markdown = f"alpha{placeholder}bravo{placeholder}charlie"

    assert _split_pages(markdown, placeholder, 3) == ["alpha", "bravo", "charlie"]


def test_split_pages_pads_when_short() -> None:
    placeholder = "<!-- page -->"
    markdown = f"alpha{placeholder}bravo"

    assert _split_pages(markdown, placeholder, 4) == ["alpha", "bravo", "", ""]


def test_split_pages_raises_when_long() -> None:
    placeholder = "<!-- page -->"
    markdown = f"alpha{placeholder}bravo{placeholder}charlie"

    with pytest.raises(ValueError):
        _split_pages(markdown, placeholder, 2)


@pytest.mark.docling
def test_csf_sample_preserves_pages_tables_and_removes_running_header() -> None:
    path = Path(__file__).parents[1] / "docs/samples/NIST.CSWP.29_CSF-2.0.pdf"

    document = DoclingParser().parse(path)

    assert document.page_count == 32
    assert document.pages is not None
    assert len(document.pages) == document.page_count
    assert (
        "This appendix describes the Functions, Categories, and Subcategories of the CSF Core."
        in document.text
    )
    assert any("GV.OC" in line and "|" in line for line in document.text.splitlines())
    assert "NIST CSWP 29 February 26, 2024" not in document.text
