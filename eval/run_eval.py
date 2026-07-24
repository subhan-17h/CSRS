"""Score the golden set against the live index and record an evaluation run."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from csrs.config import PROJECT_ROOT, settings
from csrs.embeddings import embed_query
from csrs.generation import generate_answer
from csrs.store import ChunkStore
from metrics import (
    chunk_matches,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    refusal_accuracy,
)
from validate_golden_set import CATEGORY_MINIMUMS, ValidationError, load_golden_set

RESULTS_DIR = Path(__file__).with_name("results")
METRIC_KEYS = ("recall_at_5", "recall_at_10", "recall_at_20", "mrr", "ndcg_at_10")
IndexedRow = tuple[str, str, dict[str, Any]]


class EvaluationError(Exception):
    """An evaluation failure that would make the reported metrics invalid."""


def positive_int(value: str) -> int:
    """Parse a positive integer for an argparse option."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse evaluation run options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-generate",
        action="store_true",
        help="skip answer generation and do not measure refusal accuracy",
    )
    parser.add_argument(
        "--depth",
        type=positive_int,
        default=settings.top_k_dense,
        help=f"retrieval depth (default: {settings.top_k_dense})",
    )
    parser.add_argument(
        "--model",
        default=settings.default_llm,
        help=f"generation model (default: {settings.default_llm})",
    )
    parser.add_argument("--label", default="baseline", help="run label (default: baseline)")
    return parser.parse_args(argv)


def scan_index(store: ChunkStore) -> tuple[list[IndexedRow], int]:
    """Read all indexed chunk IDs, texts, and metadata in one collection scan."""
    result = store._collection.get(include=["documents", "metadatas"])
    documents = result["documents"] or []
    metadatas = result["metadatas"] or []
    rows = list(zip(result["ids"], documents, metadatas, strict=True))
    document_names = {metadata["doc_name"] for metadata in metadatas}
    if not document_names:
        raise EvaluationError("the live index contains no documents")
    return rows, len(document_names)


def resolve_relevant_ids(
    pairs: list[dict[str, Any]],
    indexed_rows: list[IndexedRow],
) -> dict[str, set[str]]:
    """Resolve each answerable pair's matchers against the complete live index."""
    resolved: dict[str, set[str]] = {}
    for pair in pairs:
        if not pair["expected"]:
            resolved[pair["id"]] = set()
            continue

        pair_ids = set()
        try:
            for matcher in pair["expected"]:
                pair_ids.update(
                    chunk_id
                    for chunk_id, text, metadata in indexed_rows
                    if chunk_matches(matcher, text, metadata)
                )
        except (TypeError, ValueError) as error:
            raise EvaluationError(f"{pair['id']}: invalid expected matcher: {error}") from error

        if not pair_ids:
            raise EvaluationError(
                f"{pair['id']}: expected matchers resolve to zero chunks; "
                "the golden set and live index have diverged"
            )
        resolved[pair["id"]] = pair_ids
    return resolved


def evaluate_pairs(
    pairs: list[dict[str, Any]],
    relevant_ids: dict[str, set[str]],
    store: ChunkStore,
    depth: int,
    model: str,
    generate: bool,
) -> list[dict[str, Any]]:
    """Retrieve, score, and optionally generate exactly once for every pair."""
    rows = []
    total = len(pairs)
    for position, pair in enumerate(pairs, start=1):
        chunks = store.search(embed_query(pair["question"]), depth)
        ranked_ids = [retrieved.chunk.id for retrieved in chunks]
        pair_relevant_ids = relevant_ids[pair["id"]]
        answerable = bool(pair["expected"])

        metric_values: dict[str, float | None] = dict.fromkeys(METRIC_KEYS)
        first_relevant_rank = None
        if answerable:
            metric_values = {
                "recall_at_5": recall_at_k(pair_relevant_ids, ranked_ids, 5),
                "recall_at_10": recall_at_k(pair_relevant_ids, ranked_ids, 10),
                "recall_at_20": recall_at_k(pair_relevant_ids, ranked_ids, 20),
                "mrr": reciprocal_rank(pair_relevant_ids, ranked_ids),
                "ndcg_at_10": ndcg_at_k(pair_relevant_ids, ranked_ids, 10),
            }
            first_relevant_rank = next(
                (
                    rank
                    for rank, chunk_id in enumerate(ranked_ids, start=1)
                    if chunk_id in pair_relevant_ids
                ),
                None,
            )

        refused = None
        if generate:
            answer = generate_answer(
                pair["question"],
                chunks[: settings.rerank_top_n],
                model,
                settings.temperature,
            )
            refused = answer.refused

        rows.append(
            {
                "id": pair["id"],
                "category": pair["category"],
                "question": pair["question"],
                "must_refuse": pair.get("must_refuse") is True,
                "answerable": answerable,
                "relevant_chunk_count": len(pair_relevant_ids),
                "ranked_chunk_ids": ranked_ids,
                "first_relevant_rank": first_relevant_rank,
                **metric_values,
                "refused": refused,
            }
        )
        print(f"[{position:>2}/{total}] {pair['id']} complete", file=sys.stderr, flush=True)
    return rows


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, int | float | None]:
    """Average retrieval metrics over the answerable rows only."""
    scored_rows = [row for row in rows if row["answerable"]]
    aggregate: dict[str, int | float | None] = {
        "pairs": len(rows),
        "answerable_pairs": len(scored_rows),
    }
    for key in METRIC_KEYS:
        aggregate[key] = (
            sum(row[key] for row in scored_rows) / len(scored_rows)
            if scored_rows
            else None
        )
    return aggregate


def aggregate_refusal(
    rows: list[dict[str, Any]],
    generate: bool,
) -> dict[str, bool | int | float | None]:
    """Return refusal counts and rates, or explicit unmeasured values."""
    must_refuse_total = sum(row["must_refuse"] for row in rows)
    answerable_total = len(rows) - must_refuse_total
    if not generate:
        return {
            "measured": False,
            "must_refuse_total": must_refuse_total,
            "correct_refusals": None,
            "answerable_total": answerable_total,
            "false_refusals": None,
            "refusal_recall": None,
            "false_refusal_rate": None,
            "overall_accuracy": None,
        }

    measured = refusal_accuracy(
        (row["must_refuse"], row["refused"]) for row in rows
    )
    return {"measured": True, **asdict(measured)}


def git_commit() -> str | None:
    """Return the current commit without allowing git failures to break a run."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def write_result(result: dict[str, Any], timestamp: datetime) -> Path:
    """Write one collision-resistant UTC result file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / timestamp.strftime("%Y%m%dT%H%M%S.%fZ.json")
    path.write_text(f"{json.dumps(result, indent=2)}\n", encoding="utf-8")
    return path


def format_metric(value: int | float | None) -> str:
    """Format a table metric or its not-applicable placeholder."""
    return "-" if value is None else f"{value:.3f}"


def print_summary(
    categories: dict[str, dict[str, int | float | None]],
    aggregate: dict[str, int | float | None],
    refusal: dict[str, bool | int | float | None],
    result_path: Path,
) -> None:
    """Print retrieval and refusal results in the validator's table style."""
    print("Evaluation results")
    print(
        f"{'category':<18} {'pairs':>5} {'scored':>6} {'Recall@5':>10} "
        f"{'Recall@10':>10} {'Recall@20':>10} {'MRR':>8} {'nDCG@10':>10}"
    )
    print(
        f"{'-' * 18} {'-' * 5} {'-' * 6} {'-' * 10} {'-' * 10} "
        f"{'-' * 10} {'-' * 8} {'-' * 10}"
    )
    for category in CATEGORY_MINIMUMS:
        values = categories[category]
        print(
            f"{category:<18} {values['pairs']:>5} {values['answerable_pairs']:>6} "
            f"{format_metric(values['recall_at_5']):>10} "
            f"{format_metric(values['recall_at_10']):>10} "
            f"{format_metric(values['recall_at_20']):>10} "
            f"{format_metric(values['mrr']):>8} "
            f"{format_metric(values['ndcg_at_10']):>10}"
        )
    print(
        f"{'TOTAL':<18} {aggregate['pairs']:>5} {aggregate['answerable_pairs']:>6} "
        f"{format_metric(aggregate['recall_at_5']):>10} "
        f"{format_metric(aggregate['recall_at_10']):>10} "
        f"{format_metric(aggregate['recall_at_20']):>10} "
        f"{format_metric(aggregate['mrr']):>8} "
        f"{format_metric(aggregate['ndcg_at_10']):>10}"
    )

    print("\nRefusal")
    if not refusal["measured"]:
        print("not measured (--no-generate)")
    else:
        correct_answers = refusal["answerable_total"] - refusal["false_refusals"]
        overall_correct = refusal["correct_refusals"] + correct_answers
        total = refusal["must_refuse_total"] + refusal["answerable_total"]
        print(
            f"{'refusal recall':<21} {format_metric(refusal['refusal_recall'])} "
            f"({refusal['correct_refusals']}/{refusal['must_refuse_total']})"
        )
        print(
            f"{'false-refusal rate':<21} "
            f"{format_metric(refusal['false_refusal_rate'])} "
            f"({refusal['false_refusals']}/{refusal['answerable_total']})"
        )
        print(
            f"{'overall accuracy':<21} {format_metric(refusal['overall_accuracy'])} "
            f"({overall_correct}/{total})"
        )
    print(f"\nResults: {result_path.relative_to(PROJECT_ROOT)}")


def run(args: argparse.Namespace) -> Path:
    """Execute an evaluation run and return its JSON path."""
    data = load_golden_set()
    pairs = data["pairs"]
    store = ChunkStore()
    indexed_rows, document_count = scan_index(store)
    relevant_ids = resolve_relevant_ids(pairs, indexed_rows)
    pair_rows = evaluate_pairs(
        pairs,
        relevant_ids,
        store,
        args.depth,
        args.model,
        not args.no_generate,
    )
    aggregate = aggregate_rows(pair_rows)
    categories = {
        category: aggregate_rows(
            [row for row in pair_rows if row["category"] == category]
        )
        for category in CATEGORY_MINIMUMS
    }
    refusal = aggregate_refusal(pair_rows, not args.no_generate)
    timestamp = datetime.now(UTC)
    result = {
        "version": data["version"],
        "label": args.label,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "git_commit": git_commit(),
        "parameters": {
            "depth": args.depth,
            "model": args.model,
            "temperature": settings.temperature,
            "generate": not args.no_generate,
            "rerank_top_n": settings.rerank_top_n,
        },
        "index": {
            "documents": document_count,
            "chunks": len(indexed_rows),
        },
        "aggregate": aggregate,
        "per_category": categories,
        "refusal": refusal,
        "pairs": pair_rows,
    }
    result_path = write_result(result, timestamp)
    print_summary(categories, aggregate, refusal, result_path)
    return result_path


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and map known data failures to a concise error."""
    args = parse_args(argv)
    try:
        run(args)
    except (EvaluationError, ValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
