"""Tests for end-to-end evaluation orchestration and failure visibility."""

from __future__ import annotations

import pytest
from eval import run as run_module
from eval.dataset import Claim, Evidence, Question

from csrs.models import Chunk, RetrievedChunk, content_hash


def _question() -> Question:
    return Question(
        id="test-question",
        question="What is required?",
        answer="The system must log events.",
        claims=[Claim(id="claim-1", text="The system must log events.")],
        evidence=[
            Evidence(
                document_path="docs/standard.pdf",
                section="Control",
                printed_page="1",
                pdf_page_index=0,
                text="The system must log events.",
            )
        ],
    )


def _retrieved() -> RetrievedChunk:
    text = "The system must log events."
    return RetrievedChunk(
        chunk=Chunk(
            id="standard.pdf:1",
            text=text,
            doc_name="standard.pdf",
            section="Control",
            page=1,
            content_hash=content_hash(text),
        ),
        score=0.9,
        rank=0,
        rrf_score=0.02,
    )


def test_exact_model_validation_rejects_missing_tag() -> None:
    inventory = {
        run_module.EMBEDDING_MODEL: "embed-digest",
        "llama3.2:latest": "model-digest",
    }

    run_module._validate_models(["llama3.2:latest"], inventory)
    with pytest.raises(run_module.EvaluationRunError, match="gemma2:2b"):
        run_module._validate_models(["gemma2:2b"], inventory)


def test_default_comparison_is_the_approved_two_models() -> None:
    args = run_module.parse_args([])

    assert args.models == ["llama3.2:latest", "qwen2.5:1.5b"]


def test_evaluate_question_preserves_successful_component_results(monkeypatch) -> None:
    monkeypatch.setattr(
        run_module,
        "rewrite_query",
        lambda question, history, model: question,
    )
    monkeypatch.setattr(
        run_module,
        "_retrieve",
        lambda question, store, sparse_index: [_retrieved()],
    )
    monkeypatch.setattr(
        run_module,
        "_generate",
        lambda client, question, context, model: "The system must log events.",
    )
    monkeypatch.setattr(
        run_module,
        "score_answer_similarity",
        lambda *args, **kwargs: {"score": 1.0, "passed": True},
    )

    result = run_module.evaluate_question(
        client=object(),
        store=object(),
        sparse_index=object(),
        judge=None,
        run_id="run-1",
        dataset_version=1,
        question=_question(),
        model="llama3.2:latest",
        model_digest="digest",
        cosine_threshold=0.75,
    )

    assert result["generated_answer"] == "The system must log events."
    assert result["metrics"]["cosine_similarity"]["score"] == 1.0
    assert result["metrics"]["retrieval_evidence"]["evidence_hit_at_5"] is True
    assert result["retrieved_chunks"][0]["used_for_generation"] is True
    assert result["errors"] == []


def test_evaluate_question_keeps_retrieval_failure_visible(monkeypatch) -> None:
    monkeypatch.setattr(
        run_module,
        "rewrite_query",
        lambda question, history, model: question,
    )

    def fail_retrieval(question, store, sparse_index):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(run_module, "_retrieve", fail_retrieval)

    result = run_module.evaluate_question(
        client=object(),
        store=object(),
        sparse_index=object(),
        judge=None,
        run_id="run-1",
        dataset_version=1,
        question=_question(),
        model="llama3.2:latest",
        model_digest="digest",
        cosine_threshold=0.75,
    )

    assert result["generated_answer"] is None
    assert result["metrics"]["retrieval_evidence"] is None
    assert result["errors"] == [
        {
            "stage": "retrieval",
            "type": "RuntimeError",
            "message": "index unavailable",
        }
    ]
    assert result["latency_ms"]["total"] is not None
