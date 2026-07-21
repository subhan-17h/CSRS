"""Document parser registry and directory ingestion helpers."""

from collections.abc import Iterator
from pathlib import Path

from csrs.loaders.base import DocumentParser
from csrs.loaders.pdf import PdfParser
from csrs.loaders.text import TextParser
from csrs.models import Document

__all__ = ("DocumentParser", "PdfParser", "TextParser", "get_parser", "iter_documents")

_PARSERS: tuple[DocumentParser, ...] = (TextParser(), PdfParser())
_PARSERS_BY_EXTENSION = {
    extension.lower(): parser for parser in _PARSERS for extension in parser.extensions
}


def get_parser(path: Path) -> DocumentParser | None:
    """Return the registered parser for a path, if its extension is supported."""
    return _PARSERS_BY_EXTENSION.get(path.suffix.lower())


def iter_documents(docs_dir: Path) -> Iterator[Document]:
    """Yield supported documents recursively in deterministic path order."""
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file():
            continue
        parser = get_parser(path)
        if parser is not None:
            yield parser.parse(path)
