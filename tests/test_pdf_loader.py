"""Tests for page-preserving PDF parsing."""

from pathlib import Path

from csrs.loaders import PdfParser, get_parser
from csrs.loaders.pdf import (
    _find_repeated_lines,
    _normalise_text,
    _render_table,
    _strip_repeated_lines,
)

_PAGE_LABELS = (
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliet",
)


def _unique_page_lines(label: str) -> list[str]:
    return [
        f"{label} {part}"
        for part in (
            "heading",
            "introduction",
            "topic",
            "body",
            "detail",
            "example",
            "discussion",
            "summary",
            "notes",
            "tail",
        )
    ]


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


def test_four_line_deep_running_boilerplate_is_removed() -> None:
    pages = [
        "Running header\nDivider\nPublication note\nDOI boilerplate\n"
        "Unique alpha\nBody apple\nDetail red\nTail north",
        "Running header\nDivider\nPublication note\nDOI boilerplate\n"
        "Unique beta\nBody banana\nDetail green\nTail south",
        "Running header\nDivider\nPublication note\nDOI boilerplate\n"
        "Unique gamma\nBody cherry\nDetail blue\nTail west",
    ]

    stripped = _strip_repeated_lines(pages)

    assert stripped == [
        "Unique alpha\nBody apple\nDetail red\nTail north",
        "Unique beta\nBody banana\nDetail green\nTail south",
        "Unique gamma\nBody cherry\nDetail blue\nTail west",
    ]


def test_varying_page_number_is_removed_without_stripping_rare_digit_heading() -> None:
    pages = [
        "SECTION 2 OVERVIEW\nUnique alpha\nCHAPTER THREE PAGE 19",
        "SECTION 2 OVERVIEW\nUnique beta\nCHAPTER THREE PAGE 20",
        "Unique gamma\nCHAPTER THREE PAGE 21",
        "Unique delta\nCHAPTER THREE PAGE 22",
        "Unique epsilon\nCHAPTER THREE PAGE 23",
    ]

    stripped = _strip_repeated_lines(pages)

    assert stripped == [
        "SECTION 2 OVERVIEW\nUnique alpha",
        "SECTION 2 OVERVIEW\nUnique beta",
        "Unique gamma",
        "Unique delta",
        "Unique epsilon",
    ]


def test_chapter_scoped_numbered_footer_in_fixed_slot_is_removed() -> None:
    pages = []
    for page_number, label in enumerate(_PAGE_LABELS, start=1):
        lines = _unique_page_lines(label)
        if page_number <= 4:
            lines[2] = f"CHAPTER TWO PAGE {page_number}"
        pages.append("\n".join(lines))

    stripped = _strip_repeated_lines(pages)

    assert _find_repeated_lines(pages) == {"CHAPTER TWO PAGE #"}
    assert all("CHAPTER TWO PAGE" not in page for page in stripped[:4])


def test_numbered_content_at_varying_boundary_slots_is_not_removed() -> None:
    pages = []
    for page_number, label in enumerate(_PAGE_LABELS, start=1):
        lines = _unique_page_lines(label)
        if page_number <= 2:
            lines[0] = f"Related Controls: AC-{page_number}."
        elif page_number <= 4:
            lines[-1] = f"Related Controls: AC-{page_number}."
        pages.append("\n".join(lines))

    stripped = _strip_repeated_lines(pages)

    assert _find_repeated_lines(pages) == set()
    assert all(
        f"Related Controls: AC-{index + 1}." in page.splitlines()
        for index, page in enumerate(stripped[:4])
    )


def test_fixed_slot_unchanging_literal_is_not_removed_as_page_stamp() -> None:
    pages = []
    for page_number, label in enumerate(_PAGE_LABELS, start=1):
        lines = _unique_page_lines(label)
        if page_number <= 4:
            lines[2] = "CONTROL"
        pages.append("\n".join(lines))

    stripped = _strip_repeated_lines(pages)

    assert _find_repeated_lines(pages) == set()
    assert all("CONTROL" in page.splitlines() for page in stripped[:4])


def test_pdf_parser_is_registered(monkeypatch) -> None:
    monkeypatch.setattr("csrs.loaders.settings.pdf_parser", "pypdf")
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
