"""Pure relevance and ranking metrics for retrieval evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from math import log2
from typing import Any

MATCHER_FIELDS: frozenset[str] = frozenset(
    {"doc_name", "control_id", "page", "section_contains", "text_contains"}
)


def chunk_matches(
    matcher: Mapping[str, Any],
    text: str,
    metadata: Mapping[str, Any],
) -> bool:
    """Return whether a chunk satisfies every field in the matcher."""
    unknown_fields = set(matcher) - MATCHER_FIELDS
    if unknown_fields:
        raise ValueError(f"unsupported matcher fields: {sorted(unknown_fields)}")

    for field in ("doc_name", "control_id", "page"):
        if field in matcher and metadata.get(field) != matcher[field]:
            return False

    section = metadata.get("section")
    if "section_contains" in matcher and (
        not isinstance(section, str) or matcher["section_contains"] not in section
    ):
        return False
    return "text_contains" not in matcher or matcher["text_contains"] in text


def _validate_ranking(
    relevant_ids: AbstractSet[str],
    ranked_ids: Sequence[str],
    k: int | None = None,
) -> None:
    if not relevant_ids:
        raise ValueError("relevant_ids must not be empty")
    if k is not None and k <= 0:
        raise ValueError("k must be positive")
    if len(ranked_ids) != len(set(ranked_ids)):
        raise ValueError("ranked_ids must not contain duplicates")


def recall_at_k(
    relevant_ids: AbstractSet[str],
    ranked_ids: Sequence[str],
    k: int,
) -> float:
    """Return the fraction of relevant IDs retrieved in the first k ranks."""
    _validate_ranking(relevant_ids, ranked_ids, k)
    hits = sum(chunk_id in relevant_ids for chunk_id in ranked_ids[:k])
    return hits / len(relevant_ids)


def reciprocal_rank(
    relevant_ids: AbstractSet[str],
    ranked_ids: Sequence[str],
) -> float:
    """Return the reciprocal rank of the first relevant ID."""
    _validate_ranking(relevant_ids, ranked_ids)
    for rank, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in relevant_ids:
            return 1 / rank
    return 0.0


def ndcg_at_k(
    relevant_ids: AbstractSet[str],
    ranked_ids: Sequence[str],
    k: int,
) -> float:
    """Return binary normalized discounted cumulative gain at k."""
    _validate_ranking(relevant_ids, ranked_ids, k)
    dcg = sum(
        1 / log2(rank + 1)
        for rank, chunk_id in enumerate(ranked_ids[:k], start=1)
        if chunk_id in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1 / log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg


@dataclass(frozen=True, slots=True)
class RefusalAccuracy:
    """Hold refusal counts and rates across answerable and refusal outcomes."""

    must_refuse_total: int
    correct_refusals: int
    answerable_total: int
    false_refusals: int
    refusal_recall: float | None
    false_refusal_rate: float | None
    overall_accuracy: float | None


def refusal_accuracy(outcomes: Iterable[tuple[bool, bool]]) -> RefusalAccuracy:
    """Return refusal counts and rates for the supplied outcomes."""
    must_refuse_total = 0
    correct_refusals = 0
    answerable_total = 0
    false_refusals = 0

    for must_refuse, refused in outcomes:
        if must_refuse:
            must_refuse_total += 1
            correct_refusals += refused
        else:
            answerable_total += 1
            false_refusals += refused

    total = must_refuse_total + answerable_total
    refusal_recall = (
        correct_refusals / must_refuse_total if must_refuse_total else None
    )
    false_refusal_rate = false_refusals / answerable_total if answerable_total else None
    overall_accuracy = (
        (correct_refusals + answerable_total - false_refusals) / total if total else None
    )
    return RefusalAccuracy(
        must_refuse_total=must_refuse_total,
        correct_refusals=correct_refusals,
        answerable_total=answerable_total,
        false_refusals=false_refusals,
        refusal_recall=refusal_recall,
        false_refusal_rate=false_refusal_rate,
        overall_accuracy=overall_accuracy,
    )
