"""Document parser registry and directory ingestion helpers."""

from collections.abc import Iterator
from pathlib import Path

from csrs.config import settings
from csrs.loaders.base import DocumentParser
from csrs.loaders.docling_parser import DoclingParser
from csrs.loaders.pdf import PdfParser
from csrs.loaders.text import TextParser
from csrs.models import Document

__all__ = (
    "DoclingParser",
    "DocumentParser",
    "PdfParser",
    "TextParser",
    "get_parser",
    "iter_document_paths",
    "iter_documents",
)

_PARSERS: tuple[DocumentParser, ...] = (TextParser(),)
_PARSERS_BY_EXTENSION = {
    extension.lower(): parser for parser in _PARSERS for extension in parser.extensions
}


def get_parser(path: Path) -> DocumentParser | None:
    """Return the registered parser for a path, if its extension is supported."""
    extension = path.suffix.lower()
    if extension == ".pdf":
        return DoclingParser() if settings.pdf_parser == "docling" else PdfParser()
    return _PARSERS_BY_EXTENSION.get(extension)


def iter_document_paths(docs_dir: Path) -> Iterator[Path]:
    """Yield supported file paths recursively without parsing their contents."""
    for path in sorted(docs_dir.rglob("*")):
        if path.is_file() and get_parser(path) is not None:
            yield path


def iter_documents(docs_dir: Path) -> Iterator[Document]:
    """Yield supported documents recursively in deterministic path order."""
    for path in iter_document_paths(docs_dir):
        parser = get_parser(path)
        if parser is not None:
            yield parser.parse(path)
