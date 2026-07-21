"""PDF document parser with page-preserving text extraction."""

import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from csrs.models import Document


def _normalise_text(text: str) -> str:
    """Return stable retrieval text while preserving paragraph boundaries."""
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" +\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _render_table(rows: Sequence[Sequence[str | None]]) -> str:
    """Render a useful extracted table as compact pipe-delimited rows."""
    width = max((len(row) for row in rows), default=0)
    cleaned = [
        [(row[index] or "").strip() if index < len(row) else "" for index in range(width)]
        for row in rows
    ]
    kept_columns = [index for index in range(width) if any(row[index] for row in cleaned)]
    non_empty_rows = [row for row in cleaned if any(row[index] for index in kept_columns)]
    if len(non_empty_rows) < 2:
        return ""
    return "\n".join(
        " | ".join(row[index] for index in kept_columns) for row in non_empty_rows
    )


def _find_repeated_lines(pages: Sequence[str]) -> set[str]:
    """Return boundary lines that occur on at least half of three or more pages."""
    if len(pages) < 3:
        return set()

    counts: dict[str, int] = {}
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        for line in set(lines[:3] + lines[-3:]):
            counts[line] = counts.get(line, 0) + 1
    return {line for line, count in counts.items() if count * 2 >= len(pages)}


def _strip_repeated_lines(pages: Sequence[str]) -> list[str]:
    """Remove detected running headers and footers from page text."""
    repeated = _find_repeated_lines(pages)
    return [
        "\n".join(line for line in page.splitlines() if line.strip() not in repeated)
        for page in pages
    ]


class PdfParser:
    """Load PDF text and tables while preserving page boundaries."""

    extensions = (".pdf",)

    def parse(self, path: Path) -> Document:
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]

        with pdfplumber.open(path) as pdf:
            for index, page in enumerate(pdf.pages):
                rendered_tables = [
                    rendered
                    for table in page.find_tables()
                    if (rendered := _render_table(table.extract()))
                ]
                if rendered_tables:
                    pages[index] = "\n\n".join(
                        part for part in (pages[index].rstrip(), "\n".join(rendered_tables)) if part
                    )

        pages = [_normalise_text(page) for page in _strip_repeated_lines(pages)]
        return Document(
            name=path.name,
            path=path,
            text="\n\n".join(pages),
            pages=pages,
            page_count=len(pages),
        )
