"""Tests for evaluation aggregation and inspectable output files."""

from __future__ import annotations

import json

from reporting import (
    append_result,
    classify_result_errors,
    read_results,
    summarize_results,
    write_reports,
)


def _result(model: str, question_id: str, *, failed: bool = False) -> dict:
    return {
        "question_id": question_id,
        "question": f"Question {question_id}?",
        "candidate_model": model,
        "candidate_model_digest": f"digest-{model}",
        "generated_answer": "Candidate answer",
        "reference_answer": "Reference answer",
        "gold_claims": [{"id": "claim-1", "text": "Required fact"}],
        "gold_evidence": [{"document_path": "docs/standard.pdf", "text": "Evidence"}],
        "retrieved_chunks": [
            {
                "id": "standard.pdf:1",
                "text": "Evidence",
                "used_for_generation": True,
            }
        ],
        "latency_ms": {"generation": 100.0},
        "metrics": {
            "cosine_similarity": {"score": 0.8, "passed": True},
            "retrieval_evidence": {
                "evidence_hit_at_5": not failed,
                "evidence_recall_at_5": 0.0 if failed else 1.0,
                "evidence_hit_at_10": True,
                "evidence_recall_at_10": 1.0,
            },
            "llm_judge": {
                "judgment": {
                    "correctness": {"score": 2 if failed else 4},
                    "completeness": {
                        "score": 2 if failed else 4,
                        "missing_claim_ids": ["claim-1"] if failed else [],
                    },
                    "faithfulness": {
                        "score": 1 if failed else 4,
                        "unsupported_claims": ["extra"] if failed else [],
                        "contradicted_claims": [],
                    },
                    "relevance": {"score": 4},
                    "verdict": "fail" if failed else "pass",
                }
            },
        },
        "errors": [{"stage": "judge", "message": "bad response"}] if failed else [],
    }


def test_jsonl_round_trip_and_summary_aggregation(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    append_result(path, _result("model-a", "q1"))
    append_result(path, _result("model-a", "q2", failed=True))

    rows = read_results(path)
    summary = summarize_results(rows)[0]

    assert len(rows) == 2
    assert summary["cosine_mean"] == 0.8
    assert summary["cosine_pass_rate"] == 1.0
    assert summary["judge_correctness_mean"] == 3.0
    assert summary["judge_pass_rate"] == 0.5
    assert summary["evidence_hit_rate_at_5"] == 0.5
    assert summary["failed_or_skipped"] == 1


def test_summary_handles_intentionally_disabled_judge() -> None:
    result = _result("model-a", "q1")
    result["metrics"]["llm_judge"] = None

    summary = summarize_results([result])[0]

    assert summary["judge_count"] == 0
    assert summary["judge_correctness_mean"] is None
    assert summary["judge_pass_rate"] is None


def test_pipeline_and_metric_failures_remain_visible() -> None:
    labels = classify_result_errors(_result("model-a", "q1", failed=True))

    assert labels == [
        "retrieval miss",
        "missing gold claim",
        "unsupported claim",
        "judge failure",
    ]


def test_reports_include_component_metrics_and_manual_review(tmp_path) -> None:
    results = [_result("model-a", "q1"), _result("model-b", "q2")]
    config = {
        "run_id": "test-run",
        "dataset_version": "1.0",
        "judge_enabled": True,
        "cosine_threshold": 0.75,
    }

    summaries = write_reports(tmp_path, config, results)

    assert len(summaries) == 2
    assert "No combined score is calculated" in (tmp_path / "report.md").read_text()
    assert "cosine_mean" in (tmp_path / "summary.csv").read_text()
    review = json.loads((tmp_path / "manual_review.json").read_text())
    assert review["sample_size"] == 2
    assert review["records"][0]["human_correctness"] is None


def test_malformed_persisted_result_fails_visibly(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    path.write_text("{}\n\n", encoding="utf-8")

    try:
        read_results(path)
    except ValueError as error:
        assert "blank result line" in str(error)
    else:
        raise AssertionError("blank JSONL result line must be rejected")
