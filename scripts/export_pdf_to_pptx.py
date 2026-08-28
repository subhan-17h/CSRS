#!/usr/bin/env python3
"""Export a 16:9 presentation PDF as an image-based PowerPoint deck."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

WIDE_RATIO = 16 / 9
RATIO_TOLERANCE = 0.005
BUNDLED_DEPENDENCIES = (
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
)
FIXED_ZIP_DATE = (2000, 1, 1, 0, 0, 0)
FIXED_CORE_DATE = b"2000-01-01T00:00:00Z"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert each page of a 16:9 presentation PDF to a high-resolution PNG "
            "and place it edge-to-edge on a PowerPoint slide."
        ),
        epilog=(
            "Example: python scripts/export_pdf_to_pptx.py "
            "latex/CSRS_Presentation.pdf CSRS_Presentation.pptx --dpi 192"
        ),
    )
    parser.add_argument("input_pdf", type=Path, help="source 16:9 presentation PDF")
    parser.add_argument("output_pptx", type=Path, help="destination .pptx path")
    parser.add_argument(
        "--dpi",
        type=int,
        default=192,
        help="raster resolution in dots per inch (default: 192)",
    )
    return parser


def _find_executable(name: str, bundled_relative: str) -> str:
    executable = shutil.which(name)
    if executable:
        return executable
    bundled = BUNDLED_DEPENDENCIES / bundled_relative
    if bundled.is_file():
        return str(bundled)
    raise RuntimeError(f"required executable not found: {name}")


def _pdf_metadata(pdfinfo: str, input_pdf: Path) -> tuple[int, float, float]:
    result = subprocess.run(
        [pdfinfo, str(input_pdf)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"pdfinfo could not read {input_pdf}: {detail}")

    pages_match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    size_match = re.search(
        r"^Page size:\s+([0-9.]+) x ([0-9.]+) pts",
        result.stdout,
        re.MULTILINE,
    )
    if pages_match is None or size_match is None:
        raise RuntimeError("pdfinfo did not report the page count and page size")
    return (
        int(pages_match.group(1)),
        float(size_match.group(1)),
        float(size_match.group(2)),
    )


def _ordered_page_images(directory: Path, expected_pages: int) -> list[Path]:
    numbered: list[tuple[int, Path]] = []
    for path in directory.glob("page-*.png"):
        match = re.fullmatch(r"page-(\d+)\.png", path.name)
        if match:
            numbered.append((int(match.group(1)), path))
    numbered.sort()
    images = [path for _, path in numbered]
    if len(images) != expected_pages:
        raise RuntimeError(
            f"pdftoppm rendered {len(images)} pages; expected {expected_pages}"
        )
    return images


def _node_environment() -> dict[str, str]:
    env = os.environ.copy()
    bundled_modules = BUNDLED_DEPENDENCIES / "node/node_modules"
    if bundled_modules.is_dir():
        paths = [path for path in env.get("NODE_PATH", "").split(os.pathsep) if path]
        if str(bundled_modules) not in paths:
            paths.append(str(bundled_modules))
        env["NODE_PATH"] = os.pathsep.join(paths)
    return env


def _normalize_pptx(source: Path, destination: Path) -> None:
    """Remove volatile package dates and use stable archive ordering."""
    date_pattern = re.compile(
        rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:(?:created|modified)>)"
    )
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as outgoing:
        for original in sorted(incoming.infolist(), key=lambda info: info.filename):
            data = incoming.read(original.filename)
            if original.filename == "docProps/core.xml":
                data = date_pattern.sub(
                    rb"\g<1>" + FIXED_CORE_DATE + rb"\g<2>",
                    data,
                )
            normalized = zipfile.ZipInfo(original.filename, FIXED_ZIP_DATE)
            normalized.compress_type = zipfile.ZIP_DEFLATED
            normalized.create_system = original.create_system
            normalized.external_attr = original.external_attr
            normalized.internal_attr = original.internal_attr
            normalized.flag_bits = original.flag_bits
            outgoing.writestr(normalized, data, compresslevel=9)


def export(input_pdf: Path, output_pptx: Path, dpi: int) -> None:
    if not input_pdf.is_file():
        raise RuntimeError(f"input PDF not found: {input_pdf}")
    if input_pdf.suffix.lower() != ".pdf":
        raise RuntimeError("input must have a .pdf extension")
    if output_pptx.suffix.lower() != ".pptx":
        raise RuntimeError("output must have a .pptx extension")
    if dpi <= 0:
        raise RuntimeError("--dpi must be a positive integer")

    pdfinfo = _find_executable("pdfinfo", "bin/override/pdfinfo")
    pdftoppm = _find_executable("pdftoppm", "bin/override/pdftoppm")
    node = _find_executable("node", "node/bin/node")
    pages, width, height = _pdf_metadata(pdfinfo, input_pdf)
    if pages < 1:
        raise RuntimeError("input PDF contains no pages")
    if height == 0 or abs((width / height) - WIDE_RATIO) > RATIO_TOLERANCE:
        raise RuntimeError(
            f"input page is {width:g} x {height:g} pt; expected a 16:9 presentation PDF"
        )

    output_pptx.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="csrs-pptx-", dir=output_pptx.parent) as temp:
        temp_dir = Path(temp)
        raster = subprocess.run(
            [
                pdftoppm,
                "-png",
                "-r",
                str(dpi),
                str(input_pdf),
                str(temp_dir / "page"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if raster.returncode != 0:
            detail = raster.stderr.strip() or raster.stdout.strip()
            raise RuntimeError(f"pdftoppm could not render {input_pdf}: {detail}")

        images = _ordered_page_images(temp_dir, pages)
        manifest = temp_dir / "pages.json"
        manifest.write_text(
            json.dumps([str(path.resolve()) for path in images], separators=(",", ":")),
            encoding="ascii",
        )
        packager = Path(__file__).with_name("pdf_to_pptx.cjs")
        package = subprocess.run(
            [node, str(packager), str(manifest), str(output_pptx.resolve())],
            capture_output=True,
            text=True,
            env=_node_environment(),
            check=False,
        )
        if package.returncode != 0:
            detail = package.stderr.strip() or package.stdout.strip()
            raise RuntimeError(f"PptxGenJS could not write {output_pptx}: {detail}")
        normalized = temp_dir / "normalized.pptx"
        _normalize_pptx(output_pptx, normalized)
        normalized.replace(output_pptx)

    print(f"Exported {pages} slides to {output_pptx}")


def main() -> int:
    args = _parser().parse_args()
    try:
        export(args.input_pdf.resolve(), args.output_pptx.resolve(), args.dpi)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
