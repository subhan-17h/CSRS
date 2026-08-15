"""Render the two deliverable-excerpt figures used by CSRS_Work_Record.tex.

Both cards are filled from the live alert-experiment artefacts under
``~/Projects/work/CIL/`` at build time -- nothing here is transcribed by hand --
and are printed to vector PDF through headless Chrome so they stay sharp.

Run with:  python3 latex/make_excerpts.py
Output:    latex/figures/excerpt_json.pdf, latex/figures/excerpt_report.pdf
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

FIGURES = Path(__file__).resolve().parent / "figures"
DELIVERABLES = Path.home() / "Projects" / "work" / "CIL"
JSON_DELIVERABLE = DELIVERABLES / "alert_rankings_rag.json"
REPORT_DELIVERABLE = DELIVERABLES / "alert_ranking_rag_report.md"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ACCENT = "#184f95"

CARD_CSS = """
@page { size: 1120px %(height)spx; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #ffffff; }
.card { width: 1120px; border: 1px solid #d8d7d2; border-radius: 10px;
        overflow: hidden; font-family: "SF Mono", Menlo, Consolas, monospace; }
.bar { background: %(accent)s; color: #ffffff; padding: 11px 18px;
       font-size: 15px; letter-spacing: .02em; display: flex;
       justify-content: space-between; align-items: baseline; }
.bar .meta { font-size: 12.5px; opacity: .82; }
.body { padding: 18px 22px 20px; background: #fbfbfa; font-size: 13.5px;
        line-height: 1.55; color: #24231f; white-space: pre-wrap; }
.k { color: %(accent)s; }
.s { color: #1f7a52; }
.n { color: #b3521c; }
.b { color: #7a3fa8; }
table { border-collapse: collapse; font-size: 13.5px; margin: 4px 0 0; }
th, td { padding: 5px 14px; text-align: left; border-bottom: 1px solid #e6e5e0; }
th { color: %(accent)s; font-weight: 600; }
td.num, th.num { text-align: right; }
h4 { font-size: 13.5px; margin: 18px 0 6px; color: #24231f; }
h4:first-child { margin-top: 0; }
"""


def _render(name: str, height: int, bar_left: str, bar_right: str, body: str) -> Path:
    page = (
        "<meta charset='utf-8'><style>"
        + CARD_CSS % {"height": height, "accent": ACCENT}
        + "</style><div class='card'><div class='bar'><span>"
        + bar_left
        + "</span><span class='meta'>"
        + bar_right
        + "</span></div><div class='body'>"
        + body
        + "</div></div>"
    )
    out = FIGURES / f"{name}.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "card.html"
        source.write_text(page, encoding="utf-8")
        subprocess.run(
            [
                CHROME,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={out}",
                source.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    return out


def _highlight(record: dict) -> str:
    """Colour a JSON record: keys, strings, numbers, and literals."""
    text = html.escape(json.dumps(record, indent=2))

    def paint(match: re.Match[str]) -> str:
        token = match.group(0)
        if match.group("key"):
            return f"<span class='k'>{token}</span>"
        if token.startswith("&quot;"):
            return f"<span class='s'>{token}</span>"
        if token in {"true", "false", "null"}:
            return f"<span class='b'>{token}</span>"
        return f"<span class='n'>{token}</span>"

    pattern = (
        r"(?P<key>&quot;[^&]*?&quot;)(?=: )"
        r"|&quot;.*?&quot;"
        r"|\btrue\b|\bfalse\b|\bnull\b"
        r"|(?<![\w.])-?\d+(?:\.\d+)?"
    )
    return re.sub(pattern, paint, text)


def json_card() -> Path:
    records = json.loads(JSON_DELIVERABLE.read_text(encoding="utf-8"))
    record = next(r for r in records if r["alert_id"] == 23)
    return _render(
        "excerpt_json",
        900,
        "alert_rankings_rag.json",
        f"record 1 of {len(records)} &middot; alert 23",
        _highlight(record),
    )


def _table(markdown_rows: list[str]) -> str:
    """Turn a GitHub-flavoured table block into an HTML table."""
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in markdown_rows
        if not re.fullmatch(r"\|[-:| ]+\|", line.strip())
    ]
    head, *body = rows
    numeric = [not cell.replace("-", "").replace(">", "").strip().isalpha() for cell in head]
    out = ["<table><tr>"]
    out += [
        f"<th class='{'num' if right else ''}'>{html.escape(cell.replace(chr(96), ''))}</th>"
        for cell, right in zip(head, numeric, strict=True)
    ]
    out.append("</tr>")
    for row in body:
        out.append("<tr>")
        out += [
            f"<td class='{'num' if right else ''}'>{html.escape(cell.replace(chr(96), ''))}</td>"
            for cell, right in zip(row, numeric, strict=True)
        ]
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _table_at(lines: list[str], start: str) -> list[str]:
    """The first pipe table at or after ``start``, up to its trailing blank line."""
    index = next(i for i, line in enumerate(lines) if line.startswith(start))
    while not lines[index].startswith("|"):
        index += 1
    end = index
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return lines[index:end]


def report_card() -> Path:
    lines = REPORT_DELIVERABLE.read_text(encoding="utf-8").splitlines()

    # The report's Corpus row enumerates all 4,039 indexed documents; the card
    # carries the manifest totals instead.
    manifest = json.loads(
        (Path(__file__).resolve().parent.parent / "chroma_db" / "manifest.json").read_text()
    )
    corpus = (
        f"| Corpus | {len(manifest):,} documents / "
        f"{sum(entry['chunk_count'] for entry in manifest.values()):,} chunks |"
    )
    metadata = [
        corpus if line.startswith("| Corpus |") else line
        for line in _table_at(lines, "## 1. Run metadata")
    ]
    metadata[0] = "| Field | Value |"
    confusion = _table_at(lines, "| Snort \\ model")
    stats = [
        line.strip("- ").replace("**", "")
        for line in lines
        if line.startswith("- Exact match") or line.startswith("- Rank distribution")
    ]

    body = (
        "<h4>1. Run metadata</h4>"
        + _table(metadata)
        + "<h4>6. Model versus Snort &mdash; confusion table (rows: Snort priority, "
        "columns: model rank)</h4>"
        + _table(confusion)
        + "<h4>"
        + html.escape(stats[0])
        + "<br>"
        + html.escape(stats[1])
        + "</h4>"
    )
    return _render(
        "excerpt_report",
        650,
        "alert_ranking_rag_report.md",
        "sections 1 and 6, regenerated from the run snapshot",
        body,
    )


if __name__ == "__main__":
    FIGURES.mkdir(parents=True, exist_ok=True)
    for path in (json_card(), report_card()):
        print(f"wrote {path}")
