#!/usr/bin/env python3
"""Download Snort rule documentation as plain-text RAG source documents.

Documentation pages use ``snort_rule_doc_`` filenames; community rule-text
documents use the collision-free ``snort_rule_`` prefix.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT.parent / "alert_sample_50.json"
DEFAULT_OUT = PROJECT_ROOT / "docs" / "samples"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = 60
MIN_BYTES = 3_000
RULE_URL_RE = re.compile(r"/(\d+)-(\d+)/?$")


@dataclass(frozen=True)
class RuleSource:
    """One Snort rule-documentation page to fetch."""

    gid: int
    sid: int
    url: str

    @property
    def filename(self) -> str:
        return f"snort_rule_doc_{self.gid}-{self.sid}.txt"


class VisibleTextParser(HTMLParser):
    """Extract readable lines while ignoring non-visible HTML content."""

    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
    SKIP_TAGS = {"head", "script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if not self._skip_depth and tag in self.BLOCK_TAGS:
            self._finish_line()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if not self._skip_depth and tag in self.BLOCK_TAGS:
            self._finish_line()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text)

    def close(self) -> None:
        super().close()
        self._finish_line()

    def _finish_line(self) -> None:
        if not self._parts:
            return
        line = " ".join(self._parts)
        line = " ".join(line.split())
        if line:
            self.lines.append(line)
        self._parts.clear()


def parse_url(url: str) -> tuple[int, int]:
    """Return the gid and sid encoded in a Snort rule-documentation URL."""
    match = RULE_URL_RE.search(url)
    if match is None:
        raise ValueError(f"URL does not end in <gid>-<sid>: {url!r}")
    return int(match.group(1)), int(match.group(2))


def collect_rule_sources(sample: dict[str, Any]) -> tuple[RuleSource, ...]:
    """Collect unique rule-documentation URLs from an alert sample."""
    entries = sample.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("sample JSON field 'entries' must be a list")

    urls: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        documentation = entry.get("rule_documentation")
        if not isinstance(documentation, dict):
            continue
        url = documentation.get("doc_url")
        if isinstance(url, str) and url:
            urls.add(url)

    sources = []
    for url in urls:
        gid, sid = parse_url(url)
        sources.append(RuleSource(gid=gid, sid=sid, url=url))
    return tuple(sorted(sources, key=lambda source: (source.gid, source.sid, source.url)))


def load_rule_sources(path: Path) -> tuple[RuleSource, ...]:
    """Load an alert sample and return its unique Snort documentation sources."""
    try:
        sample = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(sample, dict):
        raise ValueError(f"sample JSON in {path} must contain an object")
    return collect_rule_sources(sample)


def extract_rule_text(html: str, gid: int, sid: int) -> str:
    """Extract the meaningful rule-document section from a Snort HTML page."""
    parser = VisibleTextParser()
    parser.feed(html)
    parser.close()

    page_marker = f"Rule Document {gid}:{sid}"
    try:
        start = next(index for index, line in enumerate(parser.lines) if page_marker in line)
    except StopIteration as exc:
        raise RuntimeError(f"page marker {page_marker!r} was not found") from exc

    try:
        end = next(
            index
            for index, line in enumerate(parser.lines[start + 1 :], start=start + 1)
            if "Privacy Policy" in line
        )
    except StopIteration as exc:
        raise RuntimeError("footer marker 'Privacy Policy' was not found") from exc

    lines = parser.lines[start:end]
    if not lines:
        raise RuntimeError("rule-document section was empty")
    return "\n".join(lines)


def render_document(source: RuleSource, rule_text: str) -> str:
    """Render one extracted rule page in the corpus text format."""
    header = (
        f"SNORT RULE DOCUMENT | rule_id: {source.gid}:{source.sid} | source: {source.url}"
    )
    return f"{header}\n\n{rule_text.rstrip()}\n"


def _get(url: str) -> bytes:
    """Fetch a URL with the browser User-Agent required by snort.org."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read()


def _validate(data: bytes) -> None:
    """Reject short responses and HTML error pages returned with HTTP 200."""
    if len(data) < MIN_BYTES:
        raise RuntimeError(
            f"only {len(data):,} bytes, expected at least {MIN_BYTES:,} "
            "- the server probably returned an error page"
        )
    if b"Rule Documentation" not in data and b"Alert Message" not in data:
        preview = data[:80].decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"rule-document marker not found (starts with {preview!r})")


def _write(path: Path, data: bytes) -> None:
    """Write atomically so an interrupted run never leaves a partial document."""
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_bytes(data)
    tmp.replace(path)


def fetch(source: RuleSource, out_dir: Path, force: bool) -> tuple[str, int]:
    """Fetch one source and return its status and byte count on disk."""
    target = out_dir / source.filename
    if target.exists() and not force:
        return "skipped", target.stat().st_size

    data = _get(source.url)
    _validate(data)
    html = data.decode("utf-8", errors="replace")
    rule_text = extract_rule_text(html, source.gid, source.sid)
    rendered = render_document(source, rule_text).encode("utf-8")
    _write(target, rendered)
    return "downloaded", len(rendered)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="alert sample JSON")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument(
        "--force", action="store_true", help="re-download even if the target already exists"
    )
    args = parser.parse_args()

    try:
        sources = load_rule_sources(args.input)
        args.out.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        print(f"FAILED: {exc}")
        return 1

    print(f"Fetching {len(sources)} Snort rule document(s) into {args.out}\n")
    failures = 0
    for source in sources:
        try:
            status, size = fetch(source, args.out, args.force)
        except (UnicodeError, urllib.error.URLError, RuntimeError, OSError) as exc:
            print(f"  {source.filename}  0 bytes  [FAILED: {exc}]")
            failures += 1
            continue
        print(f"  {source.filename}  {size:,} bytes  [{status}]")

    if failures:
        print(f"\n{failures} of {len(sources)} rule document(s) failed.")
        return 1
    print(f"\nAll {len(sources)} rule document(s) are present in {args.out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
