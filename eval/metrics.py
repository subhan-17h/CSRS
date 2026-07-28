"""The three small, independent metric layers used by the evaluation command."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from csrs.models import RetrievedChunk

ANSWER_SIMILARITY_PREFIX = "clustering: "
DEFAULT_COSINE_THRESHOLD = 0.75
EVIDENCE_TOKEN_RECALL_MIN = 0.90

Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


class MetricError(ValueError):
    """A metric input cannot produce a valid score."""


def normalize_whitespace(text: str) -> str:
    """Normalize layout whitespace without changing meaningful answer tokens."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity for two non-empty, equal-length vectors."""
    if not left or not right:
        raise MetricError("cosine vectors must not be empty")
    if len(left) != len(right):
        raise MetricError(
            f"cosine vector dimensions differ: {len(left)} != {len(right)}"
        )
    if any(not math.isfinite(value) for value in [*left, *right]):
        raise MetricError("cosine vectors must contain only finite values")

    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise MetricError("cosine vectors must have non-zero norms")
    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    return dot_product / (left_norm * right_norm)


def score_answer_similarity(
    candidate_answer: str,
    reference_answers: Sequence[str],
    embedder: Embedder,
    *,
    threshold: float = DEFAULT_COSINE_THRESHOLD,
) -> dict[str, Any]:
    """Score one answer against all references and retain the best reference."""
    candidate = normalize_whitespace(candidate_answer)
    references = [normalize_whitespace(reference) for reference in reference_answers]
    if not candidate:
        raise MetricError("candidate answer must not be empty")
    if not references or any(not reference for reference in references):
        raise MetricError("reference answers must not be empty")
    if not -1.0 <= threshold <= 1.0:
        raise MetricError("cosine threshold must be between -1 and 1")

    prefixed = [
        f"{ANSWER_SIMILARITY_PREFIX}{text}" for text in [candidate, *references]
    ]
    vectors = [list(vector) for vector in embedder(prefixed)]
    if len(vectors) != len(prefixed):
        raise MetricError(
            f"embedding count differs: expected {len(prefixed)}, got {len(vectors)}"
        )

    candidate_vector = vectors[0]
    scores = [
        cosine_similarity(candidate_vector, reference_vector)
        for reference_vector in vectors[1:]
    ]
    selected_index = max(range(len(scores)), key=scores.__getitem__)
    score = scores[selected_index]
    return {
        "score": score,
        "threshold": threshold,
        "threshold_is_provisional": True,
        "passed": score >= threshold,
        "selected_reference": references[selected_index],
        "selected_reference_index": selected_index,
    }


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return set(re.findall(r"[a-z0-9]+", normalized))


def evidence_token_recall(evidence_text: str, chunk_text: str) -> float:
    """Return the fraction of distinct gold-evidence tokens present in a chunk."""
    evidence_tokens = _tokens(evidence_text)
    if not evidence_tokens:
        raise MetricError("gold evidence must contain at least one alphanumeric token")
    return len(evidence_tokens & _tokens(chunk_text)) / len(evidence_tokens)


def chunk_matches_evidence(
    evidence: Mapping[str, Any],
    retrieved: RetrievedChunk,
    *,
    minimum_token_recall: float = EVIDENCE_TOKEN_RECALL_MIN,
) -> bool:
    """Match one indexed chunk to one corpus-grounded evidence record."""
    if not 0.0 <= minimum_token_recall <= 1.0:
        raise MetricError("minimum evidence token recall must be between 0 and 1")

    document_path = evidence.get("document_path")
    evidence_text = evidence.get("text")
    pdf_page_index = evidence.get("pdf_page_index")
    if not isinstance(document_path, str) or not document_path:
        raise MetricError("gold evidence requires document_path")
    if not isinstance(evidence_text, str) or not evidence_text:
        raise MetricError("gold evidence requires text")
    if pdf_page_index is not None and (
        not isinstance(pdf_page_index, int) or isinstance(pdf_page_index, bool)
    ):
        raise MetricError("pdf_page_index must be an integer or null")

    chunk = retrieved.chunk
    if chunk.doc_name != Path(document_path).name:
        return False
    if pdf_page_index is not None and chunk.page != pdf_page_index + 1:
        return False
    return (
        evidence_token_recall(evidence_text, chunk.text) >= minimum_token_recall
    )


def score_retrieval_evidence(
    evidence_items: Sequence[Mapping[str, Any]],
    retrieved_chunks: Sequence[RetrievedChunk],
    *,
    depths: Sequence[int] = (5, 10),
) -> dict[str, Any]:
    """Report evidence hit and recall independently at each requested depth."""
    if not evidence_items:
        raise MetricError("retrieval evaluation requires gold evidence")
    if not depths or any(depth <= 0 for depth in depths):
        raise MetricError("retrieval depths must be positive")

    matches = []
    for evidence_index, evidence in enumerate(evidence_items):
        matching_ranks = [
            rank + 1
            for rank, retrieved in enumerate(retrieved_chunks)
            if chunk_matches_evidence(evidence, retrieved)
        ]
        matches.append(
            {
                "evidence_index": evidence_index,
                "matching_ranks": matching_ranks,
            }
        )

    result: dict[str, Any] = {"matches": matches}
    for depth in sorted(set(depths)):
        matched_count = sum(
            any(rank <= depth for rank in match["matching_ranks"])
            for match in matches
        )
        result[f"evidence_hit_at_{depth}"] = matched_count > 0
        result[f"evidence_recall_at_{depth}"] = matched_count / len(evidence_items)
    return result
