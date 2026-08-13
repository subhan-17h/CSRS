#!/usr/bin/env python3
"""Download Snort 3 community rules as one RAG document per rule.

This downloader is stdlib-only. It reads the community ruleset from a GitHub
mirror, extracts the rules file in memory, and writes each rule atomically as
``snort_rule_1-<sid>.txt``.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "docs" / "samples"

TARBALL_URL = (
    "https://raw.githubusercontent.com/mrkaban/mirror-snort3-community-rules/"
    "main/snort3-community-rules.tar.gz"
)
RULES_MEMBER = "snort3-community.rules"
USER_AGENT = "csrs-fetch-snort-community-rules/1.0"
TIMEOUT = 120
MIN_RULES_BYTES = 50_000
SID_RE = re.compile(r"\bsid:(\d+)\s*;")


def parse_rules(text: str) -> tuple[dict[str, str], ...]:
    """Return the first rule line found for each numeric sid."""
    rules: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = SID_RE.search(line)
        if match is None:
            continue
        sid = match.group(1)
        if sid in seen:
            continue
        seen.add(sid)
        rules.append({"sid": sid, "rule_text": line})
    return tuple(rules)


def render_document(sid: str, rule_text: str) -> str:
    """Render one community rule in the corpus text format."""
    header = (
        f"SNORT RULE DOCUMENT | rule_id: 1:{sid} | source: snort3-community.rules"
    )
    return f"{header}\n\n{rule_text}\n"


def _get(url: str) -> bytes:
    """Download a URL with a browser-compatible User-Agent."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read()


def _extract_rules_text(data: bytes) -> str:
    """Extract and validate the rules text from the downloaded tarball."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            # Mirrors wrap the rules file in a top-level directory; match on the
            # member basename so the layout does not matter.
            try:
                member = next(
                    info
                    for info in archive.getmembers()
                    if info.name.split("/")[-1] == RULES_MEMBER
                )
            except StopIteration as exc:
                raise RuntimeError(f"tarball does not contain {RULES_MEMBER}") from exc
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"tarball member {member.name} is not a regular file")
            rules_data = extracted.read()
    except tarfile.TarError as exc:
        raise RuntimeError(f"invalid ruleset tarball: {exc}") from exc

    if len(rules_data) < MIN_RULES_BYTES:
        raise RuntimeError(
            f"extracted rules text is only {len(rules_data):,} bytes, expected at least "
            f"{MIN_RULES_BYTES:,}"
        )
    return rules_data.decode("utf-8", errors="replace")


def _write(path: Path, text: str) -> None:
    """Write text atomically so interrupted runs do not leave corpus files."""
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def write_rules(
    rules: tuple[dict[str, str], ...], out_dir: Path, force: bool = False
) -> tuple[int, int, list[str]]:
    """Write parsed rules and return counts for written, skipped, and failed files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    failed: list[str] = []

    for rule in rules:
        filename = f"snort_rule_1-{rule['sid']}.txt"
        target = out_dir / filename
        if target.exists() and not force:
            print(f"  {filename}  [skipped]")
            skipped += 1
            continue
        try:
            rendered = render_document(rule["sid"], rule["rule_text"])
            _write(target, rendered)
        except OSError as exc:
            print(f"  {filename}  [FAILED: {exc}]")
            failed.append(filename)
            continue
        print(f"  {filename}  {len(rendered.encode('utf-8')):,} bytes  [written]")
        written += 1

    return written, skipped, failed


def fetch_sources(out_dir: Path, force: bool) -> tuple[int, list[str]]:
    """Download, parse, and write the ruleset; return written count and failures."""
    data = _get(TARBALL_URL)
    rules = parse_rules(_extract_rules_text(data))
    if not rules:
        print("Rules parsed: 0; files written: 0; skipped: 0")
        raise RuntimeError("ruleset did not contain any rules with a sid")

    written, skipped, failed = write_rules(rules, out_dir, force)
    print(
        f"Rules parsed: {len(rules):,}; files written: {written:,}; "
        f"skipped: {skipped:,}"
    )
    return written, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument(
        "--force", action="store_true", help="re-download and overwrite existing rule files"
    )
    args = parser.parse_args()

    print(f"Fetching Snort 3 community rules into {args.out}\n")
    try:
        _, failures = fetch_sources(args.out, args.force)
    except (OSError, RuntimeError, UnicodeError, urllib.error.URLError) as exc:
        print(f"FAILED: {exc}")
        return 1
    if failures:
        print(f"{len(failures):,} rule file(s) failed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
