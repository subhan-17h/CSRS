"""Tests for end-to-end evaluation orchestration and failure visibility."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from eval import run as run_module
from eval.dataset import (
    DEFAULT_MANIFEST,
    Claim,
    Evidence,
    Question,
    load_corpus_manifest,
)
from eval.judge import QUOTA_ERROR_MESSAGE, JudgeQuotaError

from csrs.models import Chunk, RetrievedChunk, content_hash


def _question() -> Question:
    return Question(
        id="test-question",
        topic="overview_applicability",
        question_type="direct",
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


def test_default_comparison_is_all_five_approved_models() -> None:
    args = run_module.parse_args([])

    assert args.models == list(run_module.CANDIDATE_MODELS)
    assert args.bert_threshold == 0.85


def test_v2_config_records_exact_metrics_and_fixed_bertscore() -> None:
    inventory = {
        model: f"digest-{index}"
        for index, model in enumerate(
            [*run_module.CANDIDATE_MODELS, run_module.EMBEDDING_MODEL]
        )
    }

    config = run_module._build_config(
        run_id="run-1",
        dataset_path=Path(run_module.DEFAULT_DATASET),
        dataset_version=2,
        dataset_review_status="draft",
        corpus_identity={
            "manifest_version": 2,
            "indexed_chunk_count": 209,
        },
        models=run_module.CANDIDATE_MODELS,
        inventory=inventory,
        limit=None,
        judge_enabled=True,
        cosine_threshold=0.75,
        bert_threshold=0.85,
        no_cache=True,
    )

    assert config["schema_version"] == 2
    assert config["dataset_review_status"] == "draft"
    assert config["corpus_identity"]["indexed_chunk_count"] == 209
    assert config["metrics"] == [
        "cosine_similarity",
        "bertscore",
        "llm_judge",
    ]
    assert config["cosine_threshold"] == 0.75
    assert config["bert_threshold"] == 0.85
    assert config["bertscore_config"]["device"] == "cpu"
    assert config["judge_temperature"] == 0
    assert config["judge_request_policy"] == {
        "max_total_attempts": 5,
        "sdk_max_retries": 0,
        "max_retry_delay_seconds": 60.0,
    }
    assert not run_module._resume_config_matches(
        {**config, "schema_version": 1},
        config,
    )


def test_corpus_identity_combines_manifest_hash_pages_and_live_chunks() -> None:
    manifest = load_corpus_manifest()
    document = manifest.documents[0]
    identity = Path(document.document_path).relative_to("docs").as_posix()

    result = run_module._build_corpus_identity(
        manifest_path=DEFAULT_MANIFEST,
        manifest=manifest,
        live_index_manifest={
            identity: {
                "hash": document.sha256,
                "page_count": document.page_count,
                "chunk_count": 209,
            }
        },
        indexed_chunk_count=209,
    )

    assert result["manifest_path"] == "eval/data/corpus_manifest.json"
    assert len(result["manifest_hash"]) == 64
    assert result["manifest_version"] == 2
    assert result["document_count"] == 1
    assert result["indexed_chunk_count"] == 209
    assert result["documents"] == [
        {
            "document_path": "docs/samples/NIST.CSWP.29_CSF-2.0.pdf",
            "sha256": "3c31f46fee98cac0c4323453e5109291a213b4de7fef8c058af9bf67f717433c",
            "page_count": 32,
            "indexed_chunk_count": 209,
        }
    ]


def test_corpus_identity_rejects_store_manifest_count_disagreement() -> None:
    manifest = load_corpus_manifest()
    document = manifest.documents[0]
    identity = Path(document.document_path).relative_to("docs").as_posix()

    with pytest.raises(run_module.EvaluationRunError, match="chunk count differs"):
        run_module._build_corpus_identity(
            manifest_path=DEFAULT_MANIFEST,
            manifest=manifest,
            live_index_manifest={
                identity: {
                    "hash": document.sha256,
                    "page_count": document.page_count,
                    "chunk_count": 208,
                }
            },
            indexed_chunk_count=209,
        )


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
    monkeypatch.setattr(
        run_module,
        "score_bert_similarity",
        lambda *args, **kwargs: {"f1": 1.0, "passed": True},
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
        bert_threshold=0.85,
        bert_scorer=object(),
    )

    assert result["generated_answer"] == "The system must log events."
    assert result["metrics"]["cosine_similarity"]["score"] == 1.0
    assert result["metrics"]["bertscore"]["f1"] == 1.0
    assert set(result["metrics"]) == {
        "cosine_similarity",
        "bertscore",
        "llm_judge",
    }
    assert result["retrieved_chunks"][0]["used_for_generation"] is True
    assert result["retrieved_chunks"][0]["matched_evidence_indices"] == [0]
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
        bert_threshold=0.85,
        bert_scorer=object(),
    )

    assert result["generated_answer"] is None
    assert result["metrics"]["bertscore"] is None
    assert result["errors"] == [
        {
            "stage": "retrieval",
            "type": "RuntimeError",
            "message": "index unavailable",
        }
    ]
    assert result["latency_ms"]["total"] is not None


def _completed_result(question_id: str = "q1") -> dict[str, object]:
    return {
        "schema_version": 2,
        "candidate_model": "llama3.2:latest",
        "question_id": question_id,
        "generated_answer": "answer",
        "metrics": {
            "cosine_similarity": {"score": 1.0},
            "bertscore": {"f1": 1.0},
            "llm_judge": {"judgment": {"verdict": "pass"}},
        },
        "errors": [],
    }


def _judge_retry_result() -> dict[str, object]:
    return {
        "schema_version": 2,
        "candidate_model": "llama3.2:latest",
        "question_id": "q1",
        "question": "What is required?",
        "generated_answer": "The system must log events.",
        "reference_answer": "The system must log events.",
        "reference_answers": [
            "The system must log events.",
            "Event logging is required.",
        ],
        "gold_claims": [{"id": "claim-1", "text": "Log events."}],
        "gold_evidence": [{"text": "The system must log events."}],
        "retrieved_chunks": [
            {
                "id": "standard.pdf:1",
                "rank": 1,
                "document": "standard.pdf",
                "section": "Control",
                "physical_page": 1,
                "text": "The system must log events.",
                "used_for_generation": True,
            }
        ],
        "metrics": {
            "cosine_similarity": {
                "score": 1.0,
                "threshold": 0.75,
                "passed": True,
            },
            "bertscore": {
                "precision": 0.9,
                "recall": 0.91,
                "f1": 0.905,
                "threshold": 0.85,
                "passed": True,
            },
            "llm_judge": None,
        },
        "latency_ms": {
            "rewrite": 1.0,
            "retrieval": 2.0,
            "generation": 3.0,
            "judge": 4.0,
            "total": 10.0,
        },
        "errors": [
            {
                "stage": "judge",
                "type": "JudgeRequestError",
                "message": "temporary failure",
            }
        ],
    }


def test_result_completeness_requires_enabled_metrics_and_no_errors() -> None:
    complete = _completed_result()

    assert run_module._result_is_complete(complete, judge_enabled=True)
    assert not run_module._result_is_complete(
        {**complete, "metrics": {**complete["metrics"], "llm_judge": None}},
        judge_enabled=True,
    )
    assert run_module._result_is_complete(
        {**complete, "metrics": {**complete["metrics"], "llm_judge": None}},
        judge_enabled=False,
    )
    assert not run_module._result_is_complete(
        {**complete, "metrics": {**complete["metrics"], "llm_judge": {}}},
        judge_enabled=True,
    )
    assert not run_module._result_is_complete(
        {**complete, "generated_answer": " "},
        judge_enabled=True,
    )
    assert not run_module._result_is_complete(
        {**complete, "errors": [{"stage": "judge"}]},
        judge_enabled=True,
    )


def test_judge_only_retry_reuses_answer_nonjudge_metrics_and_grounding(
    monkeypatch,
) -> None:
    result = _judge_retry_result()
    original_answer = result["generated_answer"]
    original_cosine = result["metrics"]["cosine_similarity"]
    original_bertscore = result["metrics"]["bertscore"]
    observed: dict[str, object] = {}

    class FakeJudge:
        def evaluate(self, **kwargs: object) -> dict[str, object]:
            observed.update(kwargs)
            return {"judgment": {"verdict": "pass"}}

    monkeypatch.setattr(
        run_module,
        "evaluate_question",
        lambda **kwargs: pytest.fail("full evaluation must not run"),
    )
    retried = run_module._retry_judge_for_result(result, FakeJudge())

    assert retried["generated_answer"] == original_answer
    assert retried["metrics"]["cosine_similarity"] == original_cosine
    assert retried["metrics"]["bertscore"] == original_bertscore
    assert retried["metrics"]["llm_judge"]["judgment"]["verdict"] == "pass"
    assert retried["errors"] == []
    assert retried["latency_ms"]["rewrite"] == 1.0
    assert retried["latency_ms"]["retrieval"] == 2.0
    assert retried["latency_ms"]["generation"] == 3.0
    assert observed["candidate_answer"] == original_answer
    assert observed["reference_answers"] == result["reference_answers"]
    assert observed["retrieved_context"][0]["source_id"] == "standard.pdf:1"
    assert result["metrics"]["llm_judge"] is None
    assert result["errors"][0]["stage"] == "judge"


def test_judge_only_retry_rejects_earlier_stage_failures() -> None:
    result = _judge_retry_result()

    assert run_module._result_can_retry_judge(result)
    assert not run_module._result_can_retry_judge(
        {**result, "generated_answer": None}
    )
    assert not run_module._result_can_retry_judge(
        {**result, "errors": [{"stage": "generation"}]}
    )
    assert not run_module._result_can_retry_judge(
        {
            **result,
            "metrics": {
                **result["metrics"],
                "bertscore": None,
            },
        }
    )


def test_judge_retry_upsert_replaces_failed_row_without_duplicate(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    failed = _judge_retry_result()
    results = [failed]
    replacement = {
        **failed,
        "metrics": {
            **failed["metrics"],
            "llm_judge": {"judgment": {"verdict": "pass"}},
        },
        "errors": [],
    }

    run_module._upsert_result(path, results, replacement)

    persisted = run_module.read_results(path)
    assert persisted == [replacement]
    assert len(persisted) == 1


def test_judged_resume_uses_partial_retry_without_ollama_or_bertscore_work(
    tmp_path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "resume-run"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "resume-run",
                "created_at": "2026-07-29T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    failed = {**_judge_retry_result(), "question_id": "test-question"}
    run_module._write_results_atomically(run_dir / "results.jsonl", [failed])
    judge_calls: list[dict[str, object]] = []
    reported: list[dict[str, object]] = []

    class FakeJudge:
        def evaluate(self, **kwargs: object) -> dict[str, object]:
            judge_calls.append(kwargs)
            return {"judgment": {"verdict": "pass"}}

    class FakeStore:
        def count(self) -> int:
            return 209

    inventory = {
        run_module.EMBEDDING_MODEL: "embed-digest",
        "llama3.2:latest": "model-digest",
    }
    dataset = SimpleNamespace(
        version=2,
        review_status="draft",
        questions=[SimpleNamespace(id="test-question")],
    )
    monkeypatch.setattr(run_module, "validate_dataset", lambda path: dataset)
    monkeypatch.setattr(run_module.ollama, "Client", lambda host: object())
    monkeypatch.setattr(run_module, "_model_inventory", lambda client: inventory)
    monkeypatch.setattr(run_module, "ChunkStore", FakeStore)
    monkeypatch.setattr(run_module, "load_corpus_manifest", lambda path: object())
    monkeypatch.setattr(run_module, "load_manifest", lambda path: {})
    monkeypatch.setattr(
        run_module,
        "_build_corpus_identity",
        lambda **kwargs: {"indexed_chunk_count": 209},
    )
    monkeypatch.setattr(run_module, "GroqJudge", lambda no_cache: FakeJudge())
    monkeypatch.setattr(run_module, "_resume_config_matches", lambda saved, requested: True)
    monkeypatch.setattr(
        run_module,
        "build_bertscore_scorer",
        lambda **kwargs: pytest.fail("BERTScore must not load"),
    )
    monkeypatch.setattr(
        run_module,
        "evaluate_question",
        lambda **kwargs: pytest.fail("full evaluation must not run"),
    )
    monkeypatch.setattr(
        run_module,
        "Pipeline",
        lambda: pytest.fail("retrieval index must not load"),
    )
    monkeypatch.setattr(
        run_module,
        "write_reports",
        lambda output, config, results: reported.extend(results),
    )
    args = run_module.parse_args(
        [
            "--models",
            "llama3.2:latest",
            "--judge",
            "--resume",
            str(run_dir),
        ]
    )

    result_dir = run_module.run_evaluation(args)

    persisted = run_module.read_results(run_dir / "results.jsonl")
    assert result_dir == run_dir
    assert len(judge_calls) == 1
    assert len(persisted) == 1
    assert len(reported) == 1
    assert persisted[0]["generated_answer"] == failed["generated_answer"]
    assert persisted[0]["metrics"]["cosine_similarity"] == failed["metrics"][
        "cosine_similarity"
    ]
    assert persisted[0]["metrics"]["bertscore"] == failed["metrics"]["bertscore"]
    assert persisted[0]["metrics"]["llm_judge"]["judgment"]["verdict"] == "pass"
    assert persisted[0]["errors"] == []


def test_quota_failure_is_upserted_then_stops_with_resume_safe_row(
    tmp_path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "resume-run"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "resume-run",
                "created_at": "2026-07-29T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    failed = {**_judge_retry_result(), "question_id": "question-1"}
    run_module._write_results_atomically(run_dir / "results.jsonl", [failed])
    judge_calls: list[dict[str, object]] = []
    report_snapshots: list[list[dict[str, object]]] = []

    class QuotaJudge:
        def evaluate(self, **kwargs: object) -> dict[str, object]:
            judge_calls.append(kwargs)
            raise JudgeQuotaError(QUOTA_ERROR_MESSAGE)

    class FakeStore:
        def count(self) -> int:
            return 209

    def write_partial_reports(output, config, results) -> None:
        report_snapshots.append(list(results))
        for name in (
            "results.csv",
            "summary.csv",
            "report.md",
            "manual_review.json",
        ):
            (output / name).write_text("refreshed", encoding="utf-8")

    inventory = {
        run_module.EMBEDDING_MODEL: "embed-digest",
        "llama3.2:latest": "model-digest",
    }
    dataset = SimpleNamespace(
        version=2,
        review_status="draft",
        questions=[
            SimpleNamespace(id="question-1"),
            SimpleNamespace(id="question-2"),
        ],
    )
    monkeypatch.setattr(run_module, "validate_dataset", lambda path: dataset)
    monkeypatch.setattr(run_module.ollama, "Client", lambda host: object())
    monkeypatch.setattr(run_module, "_model_inventory", lambda client: inventory)
    monkeypatch.setattr(run_module, "ChunkStore", FakeStore)
    monkeypatch.setattr(run_module, "load_corpus_manifest", lambda path: object())
    monkeypatch.setattr(run_module, "load_manifest", lambda path: {})
    monkeypatch.setattr(
        run_module,
        "_build_corpus_identity",
        lambda **kwargs: {"indexed_chunk_count": 209},
    )
    monkeypatch.setattr(run_module, "GroqJudge", lambda no_cache: QuotaJudge())
    monkeypatch.setattr(run_module, "_resume_config_matches", lambda saved, requested: True)
    monkeypatch.setattr(
        run_module,
        "build_bertscore_scorer",
        lambda **kwargs: pytest.fail("second pair must not start"),
    )
    monkeypatch.setattr(
        run_module,
        "evaluate_question",
        lambda **kwargs: pytest.fail("second pair must not start"),
    )
    monkeypatch.setattr(
        run_module,
        "write_reports",
        write_partial_reports,
    )
    args = run_module.parse_args(
        [
            "--models",
            "llama3.2:latest",
            "--judge",
            "--resume",
            str(run_dir),
        ]
    )

    with pytest.raises(run_module.EvaluationRunError, match="partial results were saved"):
        run_module.run_evaluation(args)

    persisted = run_module.read_results(run_dir / "results.jsonl")
    assert len(judge_calls) == 1
    assert len(report_snapshots) == 1
    assert report_snapshots[0] == persisted
    assert all(
        (run_dir / name).read_text(encoding="utf-8") == "refreshed"
        for name in (
            "results.csv",
            "summary.csv",
            "report.md",
            "manual_review.json",
        )
    )
    assert len(persisted) == 1
    assert persisted[0]["question_id"] == "question-1"
    assert persisted[0]["errors"] == [
        {
            "stage": "judge",
            "type": "JudgeQuotaError",
            "message": QUOTA_ERROR_MESSAGE,
        }
    ]
    assert run_module._result_can_retry_judge(persisted[0])


def test_upsert_replaces_failed_row_atomically(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    results = [
        {
            **_completed_result(),
            "generated_answer": None,
            "errors": [{"stage": "generation"}],
        },
        _completed_result("q2"),
    ]
    replacement = _completed_result()

    run_module._upsert_result(path, results, replacement)

    persisted = run_module.read_results(path)
    assert len(persisted) == 2
    assert persisted == results
    assert sum(row["question_id"] == "q1" for row in persisted) == 1
    assert not path.with_suffix(".tmp").exists()
