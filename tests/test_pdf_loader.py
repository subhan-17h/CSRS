"""Tests for page-preserving PDF parsing."""

from pathlib import Path

from csrs.loaders import PdfParser, get_parser
from csrs.loaders.pdf import (
    _find_repeated_lines,
    _normalise_text,
    _render_table,
    _strip_repeated_lines,
)


def test_normalisation_folds_ligatures_and_collapses_whitespace() -> None:
    text = "of\ufb01ce\u00ad\t  controls  \n\n\n\nready   "

    assert _normalise_text(text) == "office controls\n\nready"


def test_pipe_rendering_cleans_cells_and_drops_empty_columns() -> None:
    rows = [
        [None, " Function ", "", " Category ", None, " ID ", ""],
        ["", " Govern (GV) ", "", " Organizational Context ", "", " GV.OC ", ""],
    ]

    assert _render_table(rows) == (
        "Function | Category | ID\nGovern (GV) | Organizational Context | GV.OC"
    )
    assert _render_table([[None, "only row"], ["", ""]]) == ""


def test_running_lines_are_removed_from_three_or_more_pages() -> None:
    pages = [
        "Running header\nUnique one\nBody one\nRunning footer",
        "Running header\nUnique two\nBody two\nRunning footer",
        "Running header\nUnique three\nBody three\nRunning footer",
    ]

    assert _find_repeated_lines(pages) == {"Running header", "Running footer"}
    assert _strip_repeated_lines(pages) == [
        "Unique one\nBody one",
        "Unique two\nBody two",
        "Unique three\nBody three",
    ]


def test_running_lines_are_not_removed_from_short_pdfs() -> None:
    pages = ["Running header\nPage one", "Running header\nPage two"]

    assert _find_repeated_lines(pages) == set()
    assert _strip_repeated_lines(pages) == pages


def test_pdf_parser_is_registered() -> None:
    assert isinstance(get_parser(Path("a.pdf")), PdfParser)


def test_csf_sample_preserves_pages_tables_and_removes_running_header() -> None:
    path = Path(__file__).parents[1] / "docs/samples/NIST.CSWP.29_CSF-2.0.pdf"

    document = PdfParser().parse(path)

    assert document.page_count == 32
    assert document.pages is not None
    assert len(document.pages) == document.page_count
    assert document.text.count("NIST CSWP 29") <= 2
    assert (
        "This appendix describes the Functions, Categories, and Subcategories of the CSF Core."
        in document.pages[19]
    )
    assert any(" | GV.OC" in line for line in document.pages[19].splitlines())
