"""Tests for evaluation aggregation and inspectable output files."""

from __future__ import annotations

import csv
import json

from reporting import (
    RESULT_CSV_FIELDS,
    append_result,
    classify_result_errors,
    read_results,
    summarize_results,
    write_reports,
    write_results_csv,
)


def _result(model: str, question_id: str, *, failed: bool = False) -> dict:
    return {
        "schema_version": 2,
        "question_id": question_id,
        "question": f"Question {question_id}?",
        "candidate_model": model,
        "candidate_model_digest": f"digest-{model}",
        "generation_config": {"temperature": 0},
        "rewritten_query": f"Rewritten {question_id}",
        "generated_answer": "Candidate answer",
        "reference_answer": "Reference answer",
        "reference_answers": ["Reference answer", "Alternative answer"],
        "gold_claims": [{"id": "claim-1", "text": "Required fact"}],
        "gold_evidence": [{"document_path": "docs/standard.pdf", "text": "Evidence"}],
        "retrieved_chunks": [
            {
                "id": "standard.pdf:1",
                "text": "Evidence",
                "used_for_generation": True,
            }
        ],
        "latency_ms": {
            "rewrite": 10.0,
            "retrieval": 20.0,
            "generation": 100.0,
            "judge": 40.0,
            "total": 200.0,
        },
        "metrics": {
            "cosine_similarity": {
                "score": 0.8,
                "threshold": 0.75,
                "passed": True,
                "selected_reference": "Reference answer",
                "selected_reference_index": 0,
            },
            "bertscore": {
                "precision": 0.7 if failed else 0.9,
                "recall": 0.6 if failed else 0.88,
                "f1": 0.65 if failed else 0.89,
                "threshold": 0.85,
                "passed": not failed,
                "selected_reference": "Alternative answer",
                "selected_reference_index": 1,
                "model_type": "roberta-large",
                "model_revision": "722cf37",
                "num_layers": 17,
                "device": "cpu",
                "idf": False,
                "rescale_with_baseline": False,
                "scorer_hash": "roberta-large_L17_no-idf_version=0.3.13",
                "package_version": "0.3.13",
            },
            "llm_judge": {
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "prompt_version": "judge_v1",
                "prompt_hash": "prompt-hash",
                "cache_key": "cache-key",
                "cache_hit": False,
                "judgment": {
                    "correctness": {
                        "score": 2 if failed else 4,
                        "justification": "Correctness reason",
                    },
                    "completeness": {
                        "score": 2 if failed else 4,
                        "justification": "Completeness reason",
                        "missing_claim_ids": ["claim-1"] if failed else [],
                    },
                    "faithfulness": {
                        "score": 1 if failed else 4,
                        "justification": "Faithfulness reason",
                        "unsupported_claims": ["extra"] if failed else [],
                        "contradicted_claims": [],
                    },
                    "relevance": {
                        "score": 4,
                        "justification": "Relevance reason",
                    },
                    "verdict": "fail" if failed else "pass",
                },
                "raw_response": "must not appear in CSV",
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
    assert summary["bertscore_precision_mean"] == 0.8
    assert summary["bertscore_recall_mean"] == 0.74
    assert summary["bertscore_f1_mean"] == 0.77
    assert summary["bertscore_pass_rate"] == 0.5
    assert summary["judge_correctness_mean"] == 3.0
    assert summary["judge_pass_rate"] == 0.5
    assert summary["generation_latency_mean_ms"] == 100.0
    assert summary["total_latency_median_ms"] == 200.0
    assert not any("evidence" in key for key in summary)
    assert summary["failed_or_skipped"] == 1


def test_summary_handles_intentionally_disabled_judge() -> None:
    result = _result("model-a", "q1")
    result["metrics"]["llm_judge"] = None

    summary = summarize_results([result])[0]

    assert summary["judge_count"] == 0
    assert summary["judge_correctness_mean"] is None
    assert summary["judge_pass_rate"] is None


def test_pipeline_and_metric_failures_remain_visible() -> None:
    result = _result("model-a", "q1", failed=True)
    result["metrics"]["retrieval_evidence"] = {"evidence_hit_at_5": False}
    labels = classify_result_errors(result)

    assert labels == [
        "missing gold claim",
        "unsupported claim",
        "judge failure",
    ]


def test_detailed_csv_flattens_audit_fields_without_raw_context(tmp_path) -> None:
    path = tmp_path / "results.csv"
    result = _result("model-a", "q1", failed=True)

    write_results_csv(path, [result])

    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)

    assert reader.fieldnames == RESULT_CSV_FIELDS
    assert len(rows) == 1
    row = rows[0]
    assert row["schema_version"] == "2"
    assert row["question"] == "Question q1?"
    assert row["reference_answer"] == "Reference answer"
    assert row["generated_answer"] == "Candidate answer"
    assert row["cosine_score"] == "0.8"
    assert row["cosine_threshold"] == "0.75"
    assert row["bertscore_precision"] == "0.7"
    assert row["bertscore_recall"] == "0.6"
    assert row["bertscore_f1"] == "0.65"
    assert row["bertscore_threshold"] == "0.85"
    assert row["judge_correctness_score"] == "2"
    assert row["judge_correctness_justification"] == "Correctness reason"
    assert row["judge_cache_key"] == "cache-key"
    assert row["judge_cache_hit"] == "False"
    assert json.loads(row["judge_missing_claim_ids"]) == ["claim-1"]
    assert json.loads(row["judge_unsupported_claims"]) == ["extra"]
    assert json.loads(row["errors"]) == [
        {"message": "bad response", "stage": "judge"}
    ]
    assert row["total_latency_ms"] == "200.0"
    assert "retrieved_chunks" not in row
    assert "raw_response" not in row
    assert "must not appear in CSV" not in path.read_text(encoding="utf-8")


def test_detailed_csv_strips_per_line_trailing_whitespace_and_uses_lf(tmp_path) -> None:
    path = tmp_path / "results.csv"
    result = _result("model-a", "q1")
    result["generated_answer"] = "First line  \nSecond line\t \n\nThird line "
    result["metrics"]["llm_judge"]["judgment"]["correctness"][
        "justification"
    ] = "Line one \nLine two\t"

    write_results_csv(path, [result])

    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert all(line == line.rstrip() for line in raw.decode("utf-8").splitlines())
    with path.open(encoding="utf-8", newline="") as source:
        row = next(csv.DictReader(source))
    assert row["generated_answer"] == "First line\nSecond line\n\nThird line"
    assert row["judge_correctness_justification"] == "Line one\nLine two"


def test_reports_include_independent_metrics_config_and_manual_review(tmp_path) -> None:
    results = [_result("model-a", "q1"), _result("model-b", "q2")]
    config = {
        "schema_version": 2,
        "run_id": "test-run",
        "created_at": "2026-07-29T00:00:00+00:00",
        "dataset_path": "eval/data/ground_truth.json",
        "dataset_hash": "dataset-sha",
        "dataset_version": 2,
        "dataset_review_status": "draft",
        "corpus_identity": {
            "manifest_path": "eval/data/corpus_manifest.json",
            "manifest_hash": "manifest-sha",
            "manifest_version": 2,
            "document_count": 1,
            "indexed_chunk_count": 209,
            "documents": [
                {
                    "document_path": "docs/samples/NIST.CSWP.29_CSF-2.0.pdf",
                    "sha256": "document-sha",
                    "page_count": 32,
                    "indexed_chunk_count": 209,
                }
            ],
        },
        "models": ["model-a", "model-b"],
        "model_digests": {
            "model-a": "digest-model-a",
            "model-b": "digest-model-b",
        },
        "embedding_model": "nomic-embed-text:latest",
        "embedding_model_digest": "embedding-digest",
        "generation_config": {
            "temperature": 0,
            "seed": 42,
            "num_ctx": 8192,
            "num_predict": 512,
            "think": False,
        },
        "retrieval_config": {
            "mode": "hybrid",
            "retrieval_limit": 10,
            "generator_context_limit": 5,
        },
        "question_limit": None,
        "metrics": ["cosine_similarity", "bertscore", "llm_judge"],
        "judge_enabled": True,
        "judge_provider": "groq",
        "judge_model": "openai/gpt-oss-120b",
        "judge_temperature": 0,
        "judge_request_policy": {
            "max_total_attempts": 5,
            "sdk_max_retries": 0,
        },
        "judge_cache_bypassed": True,
        "cosine_threshold": 0.75,
        "bert_threshold": 0.85,
        "bertscore_config": {
            "package": "bert-score",
            "model": "FacebookAI/roberta-large",
            "model_revision": "722cf37",
            "num_layers": 17,
            "device": "cpu",
            "idf": False,
            "rescale_with_baseline": False,
            "scorer_hash": "roberta-large_L17_no-idf_version=0.3.13",
            "package_version": "0.3.13",
        },
    }

    summaries = write_reports(tmp_path, config, results)

    assert len(summaries) == 2
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "**No combined score or overall pass is calculated.**" in report
    assert (
        "- Dataset: `eval/data/ground_truth.json`; SHA-256 `dataset-sha`; version "
        "`2`; review status `draft`; 2 result rows"
    ) in report
    assert (
        "- Corpus manifest: `eval/data/corpus_manifest.json`; SHA-256 "
        "`manifest-sha`; version `2`; documents `1`; indexed chunks `209`"
    ) in report
    assert (
        "- Corpus document: `docs/samples/NIST.CSWP.29_CSF-2.0.pdf`; SHA-256 "
        "`document-sha`; pages `32`; indexed chunks `209`"
    ) in report
    assert (
        "- Embedding model: `nomic-embed-text:latest`; digest `embedding-digest`"
    ) in report
    assert (
        '- Candidate models: `["model-a","model-b"]`; digests '
        '`{"model-a":"digest-model-a","model-b":"digest-model-b"}`'
    ) in report
    assert (
        '- Generation settings: `{"num_ctx":8192,"num_predict":512,"seed":42,'
        '"temperature":0,"think":false}`'
    ) in report
    assert (
        '- Retrieval settings: `{"generator_context_limit":5,"mode":"hybrid",'
        '"retrieval_limit":10}`'
    ) in report
    assert "Cosine similarity: threshold `0.75`" in report
    assert "BERTScore: threshold `0.85`" in report
    assert "package `bert-score` `0.3.13`" in report
    assert "Question limit: `all`" in report
    assert (
        "provider `groq`; model `openai/gpt-oss-120b`; temperature `0`; "
        "request policy"
    ) in report
    assert "cache bypassed `True`" in report
    assert "## Answer similarity" in report
    assert "## LLM judge" in report
    assert "## Latency and technical failures" in report
    assert "Hit@5" not in report
    assert "Recall@10" not in report
    summary_csv = (tmp_path / "summary.csv").read_text(encoding="utf-8")
    assert "cosine_mean" in summary_csv
    assert "bertscore_precision_mean" in summary_csv
    assert "bertscore_pass_rate" in summary_csv
    assert "evidence_hit" not in summary_csv
    with (tmp_path / "results.csv").open(encoding="utf-8", newline="") as source:
        assert len(list(csv.DictReader(source))) == 2
    assert b"\r\n" not in (tmp_path / "results.csv").read_bytes()
    assert b"\r\n" not in (tmp_path / "summary.csv").read_bytes()
    review = json.loads((tmp_path / "manual_review.json").read_text())
    assert review["sample_size"] == 2
    assert review["records"][0]["human_correctness"] is None


def test_detailed_csv_writes_stable_header_when_results_are_empty(tmp_path) -> None:
    path = tmp_path / "results.csv"

    write_results_csv(path, [])

    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        assert reader.fieldnames == RESULT_CSV_FIELDS
        assert list(reader) == []


def test_malformed_persisted_result_fails_visibly(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    path.write_text("{}\n\n", encoding="utf-8")

    try:
        read_results(path)
    except ValueError as error:
        assert "blank result line" in str(error)
    else:
        raise AssertionError("blank JSONL result line must be rejected")
