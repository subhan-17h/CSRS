"""Focused tests for the three-layer evaluator's deterministic metrics."""

from __future__ import annotations

import math

import pytest

from csrs.models import Chunk, RetrievedChunk, content_hash
from metrics import (
    ANSWER_SIMILARITY_PREFIX,
    MetricError,
    chunk_matches_evidence,
    cosine_similarity,
    score_answer_similarity,
    score_retrieval_evidence,
)


def _retrieved(
    chunk_id: str,
    text: str,
    *,
    doc_name: str = "standard.pdf",
    page: int | None = 3,
) -> RetrievedChunk:
    chunk = Chunk(
        id=chunk_id,
        text=text,
        doc_name=doc_name,
        page=page,
        content_hash=content_hash(text),
    )
    return RetrievedChunk(chunk=chunk, score=0.9, rank=0)


def test_cosine_similarity_known_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


@pytest.mark.parametrize(
    ("left", "right", "message"),
    [
        ([], [1.0], "must not be empty"),
        ([0.0], [1.0], "non-zero norms"),
        ([1.0], [1.0, 2.0], "dimensions differ"),
        ([math.nan], [1.0], "finite"),
    ],
)
def test_cosine_similarity_rejects_invalid_vectors(
    left: list[float],
    right: list[float],
    message: str,
) -> None:
    with pytest.raises(MetricError, match=message):
        cosine_similarity(left, right)


def test_answer_similarity_uses_symmetric_prefix_and_best_reference() -> None:
    observed: list[str] = []

    def embedder(texts: list[str]) -> list[list[float]]:
        observed.extend(texts)
        return [[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]]

    result = score_answer_similarity(
        "candidate",
        ["weak reference", "best reference"],
        embedder,
        threshold=0.95,
    )

    assert all(text.startswith(ANSWER_SIMILARITY_PREFIX) for text in observed)
    assert result["selected_reference"] == "best reference"
    assert result["selected_reference_index"] == 1
    assert result["score"] == pytest.approx(0.9938837347)
    assert result["passed"] is True
    assert result["threshold_is_provisional"] is True


def test_answer_similarity_rejects_empty_answer_and_bad_embedding_count() -> None:
    with pytest.raises(MetricError, match="candidate answer"):
        score_answer_similarity("", ["reference"], lambda _: [])

    with pytest.raises(MetricError, match="embedding count"):
        score_answer_similarity("answer", ["reference"], lambda _: [[1.0]])


def test_evidence_matching_requires_document_page_and_token_coverage() -> None:
    evidence = {
        "document_path": "docs/standard.pdf",
        "pdf_page_index": 2,
        "text": "Identify report and correct system flaws",
    }
    matching = _retrieved(
        "standard.pdf:1",
        "The organization shall identify, report, and correct system flaws.",
    )
    wrong_page = matching.model_copy(
        update={"chunk": matching.chunk.model_copy(update={"page": 4})}
    )
    wrong_document = _retrieved(
        "other.pdf:1",
        matching.chunk.text,
        doc_name="other.pdf",
    )

    assert chunk_matches_evidence(evidence, matching)
    assert not chunk_matches_evidence(evidence, wrong_page)
    assert not chunk_matches_evidence(evidence, wrong_document)


def test_retrieval_evidence_scores_each_gold_span_at_each_depth() -> None:
    chunks = [
        _retrieved(f"standard.pdf:{index}", f"irrelevant text {index}")
        for index in range(6)
    ]
    chunks[1] = _retrieved("standard.pdf:hit-1", "alpha beta gamma delta")
    chunks[5] = _retrieved("standard.pdf:hit-2", "one two three four")
    evidence = [
        {
            "document_path": "docs/standard.pdf",
            "pdf_page_index": 2,
            "text": "alpha beta gamma delta",
        },
        {
            "document_path": "docs/standard.pdf",
            "pdf_page_index": 2,
            "text": "one two three four",
        },
    ]

    result = score_retrieval_evidence(evidence, chunks, depths=(5, 10))

    assert result["evidence_hit_at_5"] is True
    assert result["evidence_recall_at_5"] == 0.5
    assert result["evidence_hit_at_10"] is True
    assert result["evidence_recall_at_10"] == 1.0
    assert result["matches"] == [
        {"evidence_index": 0, "matching_ranks": [2]},
        {"evidence_index": 1, "matching_ranks": [6]},
    ]
