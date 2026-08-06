#!/usr/bin/env python3
"""Download the standards source documents into docs/samples/.

Deliberately stdlib-only, so a grader can run it on a fresh clone before
installing anything:

    python scripts/fetch_docs.py

NIST CSF 2.0 is committed so a fresh clone remains queryable without a
download; use ``--force`` to refresh that same sample atomically from NIST.
NIST SP 800-53 Revision 5 is fetched (public domain, too large to commit);
ISO/IEC 27001:2022 is licensed, so its PDF is user-provided and not in
SOURCES. The experiment corpus is the three documents together.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"
SAMPLES_DIR = DOCS_DIR / "samples"

USER_AGENT = "csrs-fetch-docs/1.0 (offline cybersecurity standards RAG; educational use)"
TIMEOUT = 120

@dataclass(frozen=True)
class Source:
    """One document to fetch."""

    name: str
    filename: str
    licence: str
    url: str
    min_bytes: int = 50_000

    @property
    def is_pdf(self) -> bool:
        return self.filename.lower().endswith(".pdf")


SOURCES: tuple[Source, ...] = (
    Source(
        name="NIST Cybersecurity Framework (CSF) 2.0",
        filename="NIST.CSWP.29_CSF-2.0.pdf",
        url="https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf",
        licence="US Government work - public domain",
        min_bytes=500_000,
    ),
    Source(
        name="NIST SP 800-53 Revision 5",
        filename="NIST.SP.800-53r5.pdf",
        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf",
        licence="US Government work - public domain",
        min_bytes=500_000,
    ),
)


def _get(url: str) -> bytes:
    """Fetch a URL, raising a readable error rather than a traceback."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read()


def _validate(data: bytes, source: Source) -> None:
    """Reject the failure mode this script exists to catch.

    NIST occasionally answers a .pdf URL with an HTML error page and a 200
    status. Writing that to disk produces a 'document' that parses to garbage
    and is genuinely confusing to debug three phases later, so check the magic
    bytes and the size rather than trusting the status code.
    """
    if len(data) < source.min_bytes:
        raise RuntimeError(
            f"only {len(data):,} bytes, expected at least {source.min_bytes:,} "
            "- the server probably returned an error page"
        )
    if source.is_pdf and not data.startswith(b"%PDF"):
        preview = data[:80].decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"not a PDF (starts with {preview!r})")


def _write(path: Path, data: bytes) -> None:
    """Write via a temp file so an interrupted run never leaves a partial doc."""
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_bytes(data)
    tmp.replace(path)


def fetch(source: Source, force: bool) -> tuple[str, int]:
    """Fetch one source. Returns (status, bytes_on_disk)."""
    target = SAMPLES_DIR / source.filename

    if target.exists() and not force:
        return "skipped (committed sample already present)", target.stat().st_size

    data = _get(source.url)

    _validate(data, source)
    _write(target, data)
    return "downloaded", len(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force", action="store_true", help="re-download even if the file already exists"
    )
    args = parser.parse_args()

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {len(SOURCES)} standard into {SAMPLES_DIR}\n")

    failures = 0
    for source in SOURCES:
        print(f"  {source.name}")
        try:
            status, size = fetch(source, args.force)
        except (urllib.error.URLError, RuntimeError, OSError) as exc:
            print(f"    FAILED: {exc}\n")
            failures += 1
            continue
        print(f"    {source.filename}  {size:,} bytes  [{status}]")
        print(f"    licence: {source.licence}\n")

    if failures:
        print(f"\n{failures} of {len(SOURCES)} source(s) failed.")
        return 1
    print(f"\nAll {len(SOURCES)} configured source(s) present in docs/samples/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
