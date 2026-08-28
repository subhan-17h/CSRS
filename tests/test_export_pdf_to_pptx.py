"""Behavior tests for the presentation PDF-to-PPTX exporter."""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def _write_two_page_wide_pdf(path: Path) -> None:
    streams = (
        b"0.85 0.92 1 rg\n0 0 160 90 re f\n",
        b"1 0.88 0.78 rg\n0 0 160 90 re f\n",
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 160 90] "
        b"/Resources << >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(streams[0]), streams[0]),
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 160 90] "
        b"/Resources << >> /Contents 6 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(streams[1]), streams[1]),
    ]

    content = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode())
        content.extend(body)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(content)


def _png_dimensions(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def _node_environment() -> dict[str, str]:
    env = os.environ.copy()
    bundled = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
    )
    env.setdefault("NODE_PATH", str(bundled))
    return env


def test_exports_each_pdf_page_as_a_full_slide_image(tmp_path: Path) -> None:
    """Catch dropped/reordered pages, wrong slide geometry, or non-full-slide images."""
    input_pdf = tmp_path / "source.pdf"
    output_pptx = tmp_path / "slides.pptx"
    _write_two_page_wide_pdf(input_pdf)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_pdf_to_pptx.py",
            str(input_pdf),
            str(output_pptx),
            "--dpi",
            "144",
        ],
        cwd=Path(__file__).parents[1],
        env=_node_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output_pptx.is_file()

    namespaces = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    with zipfile.ZipFile(output_pptx) as archive:
        slide_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        media_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/media/") and not name.endswith("/")
        )
        assert slide_names == ["ppt/slides/slide1.xml", "ppt/slides/slide2.xml"]
        assert len(media_names) == 2
        assert [_png_dimensions(archive.read(name)) for name in media_names] == [
            (320, 180),
            (320, 180),
        ]

        presentation = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
        slide_size = presentation.find("p:sldSz", namespaces)
        assert slide_size is not None
        assert slide_size.attrib == {"cx": "12192000", "cy": "6858000"}

        for slide_name in slide_names:
            slide = ElementTree.fromstring(archive.read(slide_name))
            offset = slide.find(".//p:pic/p:spPr/a:xfrm/a:off", namespaces)
            extent = slide.find(".//p:pic/p:spPr/a:xfrm/a:ext", namespaces)
            assert offset is not None and offset.attrib == {"x": "0", "y": "0"}
            assert extent is not None and extent.attrib == slide_size.attrib


def test_same_pdf_exports_byte_identically(tmp_path: Path) -> None:
    """Catch variable package timestamps or metadata in repeat exports."""
    input_pdf = tmp_path / "source.pdf"
    first_pptx = tmp_path / "first.pptx"
    second_pptx = tmp_path / "second.pptx"
    _write_two_page_wide_pdf(input_pdf)
    command = [sys.executable, "scripts/export_pdf_to_pptx.py", str(input_pdf)]

    first = subprocess.run(
        [*command, str(first_pptx), "--dpi", "72"],
        cwd=Path(__file__).parents[1],
        env=_node_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    time.sleep(1.1)
    second = subprocess.run(
        [*command, str(second_pptx), "--dpi", "72"],
        cwd=Path(__file__).parents[1],
        env=_node_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr

    assert first_pptx.read_bytes() == second_pptx.read_bytes()
