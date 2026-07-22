"""Page-preserving PDF parsing with Docling's structural layout model."""

from functools import cache
from pathlib import Path
from uuid import uuid4

from csrs.config import settings
from csrs.models import Document


class DoclingSetupError(RuntimeError):
    """Report an actionable remedy when Docling is not ready to run offline."""


def _split_pages(markdown: str, placeholder: str, page_count: int) -> list[str]:
    """Split one Markdown export into exactly the number of converted PDF pages."""
    pages = markdown.split(placeholder)
    if len(pages) < page_count:
        pages.extend("" for _ in range(page_count - len(pages)))
    elif len(pages) > page_count:
        raise ValueError(
            "Docling Markdown export produced "
            f"{len(pages)} page segments for a {page_count}-page PDF"
        )
    return pages


@cache
def _build_converter(artifacts_path: Path) -> object:
    """Build and cache the expensive Docling converter for one artifacts directory."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise DoclingSetupError(
            "Docling is not installed. Run `uv sync`, or set CSRS_PDF_PARSER=pypdf "
            "to use the fallback parser."
        ) from exc

    try:
        artifacts_available = artifacts_path.is_dir() and any(artifacts_path.iterdir())
    except OSError as exc:
        raise DoclingSetupError(
            f"Docling model artifacts are not readable at {artifacts_path}. Run "
            "`uv run docling-tools models download`, or set CSRS_PDF_PARSER=pypdf "
            "to use the fallback parser."
        ) from exc
    if not artifacts_available:
        raise DoclingSetupError(
            f"Docling model artifacts are missing or empty at {artifacts_path}. Run "
            "`uv run docling-tools models download`, or set CSRS_PDF_PARSER=pypdf "
            "to use the fallback parser."
        )

    opts = PdfPipelineOptions(artifacts_path=artifacts_path, do_ocr=False)
    opts.do_table_structure = True
    opts.table_structure_options.do_cell_matching = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


class DoclingParser:
    """Parse digital-native PDFs into structural Markdown with page provenance."""

    extensions = (".pdf",)

    def parse(self, path: Path) -> Document:
        """Return a page-preserving document produced by one Markdown export."""
        converter = _build_converter(settings.docling_artifacts_path)
        doc = converter.convert(path).document  # type: ignore[attr-defined]
        placeholder = f"<!-- CSRS_PAGE_BREAK_{uuid4().hex} -->"
        markdown = doc.export_to_markdown(
            page_break_placeholder=placeholder,
            escape_html=False,
            image_placeholder="",
        )
        pages = _split_pages(markdown, placeholder, len(doc.pages))
        return Document(
            name=path.name,
            path=path,
            text="\n\n".join(pages),
            pages=pages,
            page_count=len(pages),
        )
