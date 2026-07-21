#!/usr/bin/env python3
"""Download the freely-redistributable cybersecurity standards into docs/.

Deliberately stdlib-only, so a grader can run it on a fresh clone before
installing anything:

    python scripts/fetch_docs.py

What this script does NOT fetch, and why, is as important as what it does:

  * CIS Controls  - free but requires registration and restricts redistribution.
                    Download it yourself and drop it into docs/; it will be
                    picked up automatically.
  * ISO/IEC 27001 - copyrighted and sold by ISO. Excluded outright. The spec
                    lists it as an example standard, but shipping it would be
                    infringement.

See docs/README.md for the full per-document licensing position.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"

USER_AGENT = "csrs-fetch-docs/1.0 (offline cybersecurity standards RAG; educational use)"
TIMEOUT = 120

OWASP_RAW = "https://raw.githubusercontent.com/OWASP/Top10/master/2021/docs/en"

# The OWASP Top 10 2021 is published as MkDocs markdown rather than a PDF, so we
# assemble the English edition into a single TXT in reading order. Order matters:
# it is what gives the assembled document a sane heading hierarchy.
OWASP_TOP10_PARTS = (
    "0x00_2021-notice.md",
    "0x01_2021-about-owasp.md",
    "A00_2021_Introduction.md",
    "A00_2021_How_to_use_the_OWASP_Top_10_as_a_standard.md",
    "A00_2021-How_to_start_an_AppSec_program_with_the_OWASP_Top_10.md",
    "A01_2021-Broken_Access_Control.md",
    "A02_2021-Cryptographic_Failures.md",
    "A03_2021-Injection.md",
    "A04_2021-Insecure_Design.md",
    "A05_2021-Security_Misconfiguration.md",
    "A06_2021-Vulnerable_and_Outdated_Components.md",
    "A07_2021-Identification_and_Authentication_Failures.md",
    "A08_2021-Software_and_Data_Integrity_Failures.md",
    "A09_2021-Security_Logging_and_Monitoring_Failures.md",
    "A10_2021-Server-Side_Request_Forgery_(SSRF).md",
    "A11_2021-Next_Steps.md",
)

OWASP_TOP10_HEADER = """OWASP Top 10:2021

Source:  https://owasp.org/Top10/
         https://github.com/OWASP/Top10 (2021/docs/en)
Licence: Creative Commons Attribution 4.0 International (CC BY 4.0)
         (c) OWASP Foundation.

Assembled from the official English markdown sources by scripts/fetch_docs.py.
Content is unmodified; the sections are concatenated in reading order.

"""


@dataclass(frozen=True)
class Source:
    """One document to fetch."""

    name: str
    filename: str
    licence: str
    url: str | None = None
    parts: tuple[str, ...] = field(default_factory=tuple)
    header: str = ""
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
        name="NIST SP 800-53 Rev. 5 (Security and Privacy Controls)",
        filename="NIST.SP.800-53r5.pdf",
        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf",
        licence="US Government work - public domain",
        min_bytes=2_000_000,
    ),
    Source(
        name="NIST SP 1299 (CSF 2.0 Quick-Start Guide)",
        filename="NIST.SP.1299.pdf",
        url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1299.pdf",
        licence="US Government work - public domain",
        min_bytes=100_000,
    ),
    Source(
        name="OWASP Top 10:2021",
        filename="OWASP_Top_10_2021.txt",
        parts=OWASP_TOP10_PARTS,
        header=OWASP_TOP10_HEADER,
        licence="CC BY 4.0 - (c) OWASP Foundation",
        min_bytes=40_000,
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
    target = DOCS_DIR / source.filename

    if target.exists() and not force:
        return "skipped (already present)", target.stat().st_size

    if source.parts:
        chunks = [source.header]
        for part in source.parts:
            url = f"{OWASP_RAW}/{urllib.parse.quote(part)}"
            chunks.append(_get(url).decode("utf-8"))
        data = "\n\n".join(chunks).encode("utf-8")
    elif source.url:
        data = _get(source.url)
    else:
        raise RuntimeError(f"{source.name} has neither a url nor parts")

    _validate(data, source)
    _write(target, data)
    return "downloaded", len(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force", action="store_true", help="re-download even if the file already exists"
    )
    args = parser.parse_args()

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {len(SOURCES)} standards into {DOCS_DIR}\n")

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

    print("Not fetched by design:")
    print("  CIS Controls    - free, but registration required and redistribution")
    print("                    restricted. Download manually into docs/ if you want it.")
    print("  ISO/IEC 27001   - copyrighted. Excluded. See docs/README.md.")

    if failures:
        print(f"\n{failures} of {len(SOURCES)} source(s) failed.")
        return 1
    print(f"\nAll {len(SOURCES)} sources present in docs/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
