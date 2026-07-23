"""Validate golden-set structure and resolve every matcher against the live index."""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from csrs.store import ChunkStore

GOLDEN_SET_PATH = Path(__file__).with_name("golden_set.yaml")
CATEGORY_MINIMUMS = {
    "exact_id": 12,
    "paraphrase": 12,
    "cross_document": 8,
    "out_of_scope": 10,
    "spec_example": 6,
}
MATCHER_FIELDS = {"doc_name", "control_id", "page", "section_contains", "text_contains"}
IndexedRow = tuple[str, str, dict[str, Any]]


class ValidationError(Exception):
    """A golden-set defect with enough context for an author to fix it."""


def fail(pair_id: str, message: str) -> None:
    """Raise a consistently formatted validation error."""
    raise ValidationError(f"{pair_id}: {message}")


def load_golden_set() -> dict[str, Any]:
    """Load and minimally validate the YAML document envelope."""
    try:
        data = yaml.safe_load(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValidationError(f"golden set could not be loaded: {error}") from error

    if not isinstance(data, dict) or set(data) != {"version", "pairs"}:
        raise ValidationError("top level must contain exactly 'version' and 'pairs'")
    if data["version"] != 1:
        raise ValidationError("version must be 1")
    if not isinstance(data["pairs"], list):
        raise ValidationError("pairs must be a list")
    return data


def matcher_ids(
    pair_id: str,
    matcher_index: int,
    matcher: Any,
    indexed_rows: list[IndexedRow],
    document_names: set[str],
) -> set[str]:
    """Return chunk IDs matching all specified fields, or fail on an invalid matcher."""
    label = f"matcher {matcher_index}"
    if not isinstance(matcher, dict):
        fail(pair_id, f"{label} must be a mapping")

    unknown_fields = set(matcher) - MATCHER_FIELDS
    if unknown_fields:
        fail(pair_id, f"{label} has unsupported fields: {sorted(unknown_fields)}")
    if not isinstance(matcher.get("doc_name"), str) or not matcher["doc_name"]:
        fail(pair_id, f"{label} must specify a non-empty doc_name")
    if matcher["doc_name"] not in document_names:
        fail(pair_id, f"{label} names a document not in the index: {matcher['doc_name']!r}")
    if len(matcher) < 2:
        fail(pair_id, f"{label} specifies only doc_name")

    control_narrowing_fields = sorted(
        {"page", "section_contains", "text_contains"} & set(matcher)
    )
    if "control_id" in matcher and control_narrowing_fields:
        fail(
            pair_id,
            f"{label} combines control_id with {control_narrowing_fields}; "
            "the control is the unit of relevance, and narrowing within it "
            "understates retrieval quality",
        )
    if "control_id" in matcher and (
        not isinstance(matcher["control_id"], str) or not matcher["control_id"]
    ):
        fail(pair_id, f"{label} control_id must be a non-empty string")
    if "page" in matcher and type(matcher["page"]) is not int:
        fail(pair_id, f"{label} page must be an integer")
    if "section_contains" in matcher and (
        not isinstance(matcher["section_contains"], str) or not matcher["section_contains"]
    ):
        fail(pair_id, f"{label} section_contains must be a non-empty string")
    if "text_contains" in matcher and (
        not isinstance(matcher["text_contains"], str) or not matcher["text_contains"]
    ):
        fail(pair_id, f"{label} text_contains must be a non-empty string")

    matches = set()
    for chunk_id, text, metadata in indexed_rows:
        if metadata["doc_name"] != matcher["doc_name"]:
            continue
        if "control_id" in matcher and metadata.get("control_id") != matcher["control_id"]:
            continue
        if "page" in matcher and metadata.get("page") != matcher["page"]:
            continue
        section = metadata.get("section")
        if "section_contains" in matcher and (
            not isinstance(section, str) or matcher["section_contains"] not in section
        ):
            continue
        if "text_contains" in matcher and matcher["text_contains"] not in text:
            continue
        matches.add(chunk_id)

    if not matches:
        fail(pair_id, f"{label} resolves to zero chunks: {matcher!r}")
    return matches


def validate_pair_shape(
    pair: Any,
    seen_ids: set[str],
) -> tuple[str, str, list[Any], list[str]]:
    """Validate fields that do not require reading the index."""
    if not isinstance(pair, dict):
        raise ValidationError("each pair must be a mapping")

    required_fields = {"id", "category", "question", "expected", "notes"}
    optional_fields = {"must_refuse", "provenance"}
    pair_id = pair.get("id")
    display_id = pair_id if isinstance(pair_id, str) and pair_id else "<missing-id>"
    missing_fields = required_fields - set(pair)
    unknown_fields = set(pair) - required_fields - optional_fields
    if missing_fields:
        fail(display_id, f"missing required fields: {sorted(missing_fields)}")
    if unknown_fields:
        fail(display_id, f"has unsupported fields: {sorted(unknown_fields)}")

    category = pair["category"]
    if not isinstance(category, str) or category not in CATEGORY_MINIMUMS:
        fail(display_id, f"unknown category: {category!r}")
    if not isinstance(pair_id, str) or not re.fullmatch(
        rf"{re.escape(category)}-\d{{3}}", pair_id
    ):
        fail(display_id, f"id must match {category}-NNN")
    if pair_id in seen_ids:
        fail(pair_id, "duplicate pair id")
    seen_ids.add(pair_id)

    if not isinstance(pair["question"], str) or not pair["question"].strip():
        fail(pair_id, "question must be a non-empty string")
    if not isinstance(pair["notes"], str) or not pair["notes"].strip():
        fail(pair_id, "notes must be a non-empty string")
    if not isinstance(pair["expected"], list):
        fail(pair_id, "expected must be a list")

    expected = pair["expected"]
    must_refuse = pair.get("must_refuse")
    if "must_refuse" in pair and must_refuse is not True:
        fail(pair_id, "must_refuse, when present, must be true")
    if category == "out_of_scope":
        if expected:
            fail(pair_id, "out_of_scope pairs must have an empty expected list")
        if must_refuse is not True:
            fail(pair_id, "out_of_scope pairs must specify must_refuse: true")
    elif not expected:
        if category != "spec_example" or must_refuse is not True:
            fail(pair_id, "non-refusal pairs must have at least one matcher")
    elif "must_refuse" in pair:
        fail(pair_id, "pairs with expected matchers must omit must_refuse")

    if category != "out_of_scope" and "provenance" not in pair:
        fail(pair_id, "non-out_of_scope pairs must specify provenance")
    provenance = pair.get("provenance", [])
    if not isinstance(provenance, list) or any(
        not isinstance(chunk_id, str) or not chunk_id for chunk_id in provenance
    ):
        fail(pair_id, "provenance must be a list of non-empty chunk ids")
    if len(provenance) != len(set(provenance)):
        fail(pair_id, "provenance contains duplicate chunk ids")
    if expected and not provenance:
        fail(pair_id, "pairs with expected matchers must have non-empty provenance")
    if not expected and provenance:
        fail(pair_id, "refusal pairs must have empty provenance")

    return pair_id, category, expected, provenance


def validate() -> tuple[Counter[str], dict[str, set[str]]]:
    """Validate the complete file and return values used by the summary table."""
    data = load_golden_set()
    store = ChunkStore()
    result = store._collection.get(include=["documents", "metadatas"])
    documents = result["documents"] or []
    metadatas = result["metadatas"] or []
    indexed_rows = list(zip(result["ids"], documents, metadatas, strict=True))
    rows_by_id = {
        chunk_id: (text, metadata) for chunk_id, text, metadata in indexed_rows
    }
    document_names = {metadata["doc_name"] for metadata in metadatas}
    if not document_names:
        raise ValidationError("the live index contains no documents")

    seen_ids: set[str] = set()
    category_counts: Counter[str] = Counter()
    category_chunk_ids: dict[str, set[str]] = defaultdict(set)

    for pair in data["pairs"]:
        pair_id, category, expected, provenance = validate_pair_shape(pair, seen_ids)
        category_counts[category] += 1
        pair_chunk_ids: set[str] = set()
        seen_matchers: list[dict[str, Any]] = []
        for index, matcher in enumerate(expected, start=1):
            if isinstance(matcher, dict) and matcher in seen_matchers:
                original_index = seen_matchers.index(matcher) + 1
                fail(
                    pair_id,
                    f"matcher {index} duplicates matcher {original_index}: {matcher!r}",
                )
            matches = matcher_ids(
                pair_id,
                index,
                matcher,
                indexed_rows,
                document_names,
            )
            seen_matchers.append(matcher)
            pair_chunk_ids.update(matches)
            category_chunk_ids[category].update(matches)

        # Provenance IDs are authoring-time audit artifacts. T-3.6 renumbers chunk IDs,
        # so this audit list and its checks are expected to be refreshed when re-chunking.
        for chunk_id in provenance:
            row = rows_by_id.get(chunk_id)
            if row is None:
                fail(pair_id, f"provenance chunk does not exist in the index: {chunk_id}")
            if chunk_id not in pair_chunk_ids:
                section = row[1].get("section")
                fail(
                    pair_id,
                    f"provenance chunk {chunk_id} is not matched by expected; "
                    f"section={section!r}",
                )

    if len(data["pairs"]) < 40:
        raise ValidationError(f"golden set has {len(data['pairs'])} pairs; at least 40 required")
    for category, minimum in CATEGORY_MINIMUMS.items():
        if category_counts[category] < minimum:
            raise ValidationError(
                f"category {category!r} has {category_counts[category]} pairs; "
                f"at least {minimum} required"
            )
    return category_counts, category_chunk_ids


def print_summary(
    category_counts: Counter[str],
    category_chunk_ids: dict[str, set[str]],
) -> None:
    """Print the successful validation summary."""
    print("Golden set valid")
    print(f"{'category':<18} {'pairs':>5} {'distinct chunks':>15}")
    print(f"{'-' * 18} {'-' * 5} {'-' * 15}")
    for category in CATEGORY_MINIMUMS:
        print(
            f"{category:<18} {category_counts[category]:>5} "
            f"{len(category_chunk_ids[category]):>15}"
        )
    print(f"{'TOTAL':<18} {sum(category_counts.values()):>5}")


def main() -> int:
    """Run validation and map failures to a non-zero process exit."""
    try:
        category_counts, category_chunk_ids = validate()
    except ValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print_summary(category_counts, category_chunk_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
