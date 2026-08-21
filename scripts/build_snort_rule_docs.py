#!/usr/bin/env python3
"""Build detailed Snort rule documents from preprocessed JSON records.

This builder is stdlib-only. It reads preprocessed rule documentation, renders
one detailed RAG document per rule, and writes each document atomically as
``snort_rule_1-<sid>.txt``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = PROJECT_ROOT / "docs" / "rule_docs_preprocessed_by_sid.json"
DEFAULT_OUT = PROJECT_ROOT / "docs" / "samples"


def _text(value: object) -> str:
    """Return stripped text, or an empty string when no text is present."""
    if value is None:
        return ""
    return str(value).strip()


def render_document(record: dict) -> str:
    """Render one preprocessed rule record in the corpus text format."""
    gid = record["gid"]
    sid = record["sid"]
    if record.get("doc_found"):
        source = record["doc_url"]
    else:
        source = "snort3-community.rules"
    sections = [f"SNORT RULE DOCUMENT | rule_id: {gid}:{sid} | source: {source}"]

    rule_category = _text(record.get("rule_category"))
    if rule_category:
        sections.append(f"Rule Category\n{rule_category}")

    alert_message = _text(record.get("alert_message_doc")) or _text(record["msg"])
    sections.append(f"Alert Message\n{alert_message}")

    rule_explanation = _text(record.get("rule_explanation"))
    if rule_explanation:
        sections.append(f"Rule Explanation\n{rule_explanation}")

    properties = []
    property_fragments = []
    for field, label in (
        ("classtype", "classtype"),
        ("action", "action"),
        ("protocol", "protocol"),
        ("service", "service"),
    ):
        value = _text(record.get(field))
        if value:
            property_fragments.append(f"{label}: {value}")
    if property_fragments:
        properties.append(" | ".join(property_fragments))

    flow_parts = []
    flow = _text(record.get("flow"))
    direction = _text(record.get("direction_label"))
    if flow:
        flow_parts.append(f"flow: {flow}")
    if direction:
        flow_parts.append(f"direction: {direction}")
    if flow_parts:
        properties.append(" | ".join(flow_parts))

    src_net = _text(record.get("src_net"))
    src_port = _text(record.get("src_port"))
    dst_net = _text(record.get("dst_net"))
    dst_port = _text(record.get("dst_port"))
    if all((src_net, src_port, dst_net, dst_port)):
        properties.append(
            f"source: {src_net}:{src_port} -> destination: {dst_net}:{dst_port}"
        )

    content_matches = _text(record.get("content_matches"))
    if content_matches:
        properties.append(f"content matches: {content_matches}")
    metadata = _text(record.get("metadata"))
    if metadata:
        properties.append(f"metadata: {metadata}")
    if properties:
        sections.append("Rule Properties\n" + "\n".join(properties))

    cve_lines = []
    cve_ids = record.get("cve_ids")
    if isinstance(cve_ids, str):
        rendered_ids = _text(cve_ids)
    elif isinstance(cve_ids, list):
        rendered_ids = ", ".join(
            _text(cve_id) for cve_id in cve_ids if _text(cve_id)
        )
    else:
        rendered_ids = ""
    if rendered_ids:
        cve_lines.append(rendered_ids)
    cve_text = _text(record.get("cve_text"))
    if cve_text:
        cve_lines.append(cve_text)
    if cve_lines:
        sections.append("CVE\n" + "\n".join(cve_lines))

    references = _text(record.get("references_text"))
    if references:
        sections.append(f"References\n{references}")

    contributors = _text(record.get("contributors"))
    if contributors:
        sections.append(f"Contributors\n{contributors}")

    sections.append(f"Rule Text\n{_text(record['rule_text'])}")
    return "\n\n".join(sections) + "\n"


def _write(path: Path, text: str) -> None:
    """Write text atomically so interrupted runs do not leave corpus files."""
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def write_documents(records: tuple[dict, ...], out_dir: Path) -> tuple[int, list[str]]:
    """Write rendered records and return the written count and failed filenames."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    failed: list[str] = []

    for index, record in enumerate(records, start=1):
        filename = f"snort_rule_1-{record['sid']}.txt"
        try:
            _write(out_dir / filename, render_document(record))
        except OSError:
            failed.append(filename)
        else:
            written += 1
        if index % 500 == 0:
            print(f"Records processed: {index:,}/{len(records):,}")

    print(f"Records read: {len(records):,}; files written: {written:,}")
    if failed:
        print(f"{len(failed):,} rule file(s) failed.")
    return written, failed


def load_records(path: Path) -> tuple[dict, ...]:
    """Load and validate records sorted by integer sid."""
    with path.open(encoding="utf-8") as source:
        data = json.load(source)

    if not isinstance(data, dict):
        raise RuntimeError("rule records JSON must be a JSON object")
    if not data:
        raise RuntimeError("rule records JSON object is empty")

    required_fields = ("sid", "gid", "msg", "rule_text")
    records = []
    for key, record in data.items():
        if not isinstance(record, dict):
            raise RuntimeError(f"record {key!r} must be a JSON object")
        for field in required_fields:
            if field not in record:
                raise RuntimeError(f"record {key!r} is missing required field {field!r}")
        records.append(record)

    try:
        return tuple(sorted(records, key=lambda record: int(record["sid"])))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("every record sid must be an integer") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="input JSON file")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args()

    try:
        records = load_records(args.json)
        _, failures = write_documents(records, args.out)
    except (OSError, RuntimeError, json.JSONDecodeError, UnicodeError) as exc:
        print(f"FAILED: {exc}")
        return 1
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
