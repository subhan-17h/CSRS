"""Focused tests for the three-layer evaluator's deterministic metrics."""

from __future__ import annotations

import math

import pytest

from csrs.models import Chunk, RetrievedChunk, content_hash
from metrics import (
    ANSWER_SIMILARITY_PREFIX,
    BERTSCORE_DEVICE,
    BERTSCORE_MODEL,
    BERTSCORE_MODEL_REVISION,
    BERTSCORE_NUM_LAYERS,
    MetricError,
    bertscore_config,
    chunk_matches_evidence,
    cosine_similarity,
    score_answer_similarity,
    score_bert_similarity,
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


class FakeBertScorer:
    def score(
        self,
        candidates: list[str],
        references: list[str],
    ) -> tuple[list[float], list[float], list[float]]:
        assert candidates == ["candidate", "candidate"]
        assert references == ["first reference", "best reference"]
        return [0.8, 0.91], [0.7, 0.89], [0.74, 0.90]


def test_bertscore_retains_full_tuple_for_best_f1_reference() -> None:
    result = score_bert_similarity(
        "candidate",
        ["first reference", "best reference"],
        FakeBertScorer(),
        threshold=0.85,
    )

    assert result == {
        "precision": 0.91,
        "recall": 0.89,
        "f1": 0.90,
        "threshold": 0.85,
        "passed": True,
        "selected_reference": "best reference",
        "selected_reference_index": 1,
    }


def test_bertscore_rejects_bad_threshold_and_wraps_scorer_failure() -> None:
    with pytest.raises(MetricError, match="threshold"):
        score_bert_similarity("answer", ["reference"], FakeBertScorer(), threshold=1.1)

    class FailingScorer:
        def score(self, candidates, references):
            raise RuntimeError("model unavailable")

    with pytest.raises(MetricError, match="model unavailable"):
        score_bert_similarity("answer", ["reference"], FailingScorer())


def test_bertscore_configuration_is_pinned_to_cpu_roberta_large() -> None:
    config = bertscore_config()

    assert config["package_version"] == "0.3.13"
    assert config["model"] == BERTSCORE_MODEL == "FacebookAI/roberta-large"
    assert config["model_revision"] == BERTSCORE_MODEL_REVISION
    assert config["num_layers"] == BERTSCORE_NUM_LAYERS == 17
    assert config["device"] == BERTSCORE_DEVICE == "cpu"
    assert config["idf"] is False
    assert config["rescale_with_baseline"] is False
    assert isinstance(config["scorer_hash"], str)
