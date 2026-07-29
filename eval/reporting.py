"""Inspectable JSONL, CSV, Markdown, and manual-review evaluation outputs."""

from __future__ import annotations

import csv
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

MANUAL_REVIEW_SEED = 42
MANUAL_REVIEW_LIMIT = 30
JUDGE_CRITERIA = ("correctness", "completeness", "faithfulness", "relevance")
LATENCY_STAGES = ("rewrite", "retrieval", "generation", "judge", "total")

RESULT_CSV_FIELDS = [
    "schema_version",
    "run_id",
    "dataset_version",
    "question_id",
    "question",
    "candidate_model",
    "candidate_model_digest",
    "generation_config",
    "rewritten_query",
    "generated_answer",
    "reference_answer",
    "reference_answers",
    "gold_claims",
    "gold_evidence",
    "cosine_score",
    "cosine_threshold",
    "cosine_passed",
    "cosine_selected_reference",
    "cosine_selected_reference_index",
    "bertscore_precision",
    "bertscore_recall",
    "bertscore_f1",
    "bertscore_threshold",
    "bertscore_passed",
    "bertscore_selected_reference",
    "bertscore_selected_reference_index",
    "judge_provider",
    "judge_model",
    "judge_prompt_version",
    "judge_prompt_hash",
    "judge_cache_key",
    "judge_cache_hit",
    "judge_correctness_score",
    "judge_correctness_justification",
    "judge_completeness_score",
    "judge_completeness_justification",
    "judge_missing_claim_ids",
    "judge_faithfulness_score",
    "judge_faithfulness_justification",
    "judge_unsupported_claims",
    "judge_contradicted_claims",
    "judge_relevance_score",
    "judge_relevance_justification",
    "judge_verdict",
    "rewrite_latency_ms",
    "retrieval_latency_ms",
    "generation_latency_ms",
    "judge_latency_ms",
    "total_latency_ms",
    "errors",
]
TRAILING_CSV_WHITESPACE = re.compile(r"[^\S\r\n]+(?=\r\n|\r|\n|$)")


def read_results(path: Path) -> list[dict[str, Any]]:
    """Read completed JSONL rows and fail on malformed persisted results."""
    if not path.exists():
        return []
    results = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            raise ValueError(f"blank result line at {line_number}")
        try:
            result = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid result JSON at line {line_number}") from error
        if not isinstance(result, dict):
            raise ValueError(f"result line {line_number} is not an object")
        results.append(result)
    return results


def append_result(path: Path, result: dict[str, Any]) -> None:
    """Persist one completed question-model result immediately."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")


def _numbers(values: Iterable[Any]) -> list[float]:
    return [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _rate(values: Sequence[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metric(result: dict[str, Any], name: str) -> dict[str, Any]:
    return _mapping(_mapping(result.get("metrics")).get(name))


def _judge_score(result: dict[str, Any], criterion: str) -> int | None:
    criterion_value = _mapping(_judgment(result).get(criterion))
    score = criterion_value.get("score")
    return score if isinstance(score, int) and not isinstance(score, bool) else None


def _judgment(result: dict[str, Any]) -> dict[str, Any]:
    return _mapping(_metric(result, "llm_judge").get("judgment"))


def _bool_values(results: Sequence[dict[str, Any]], metric: str) -> list[bool]:
    return [
        passed
        for result in results
        if isinstance(passed := _metric(result, metric).get("passed"), bool)
    ]


def summarize_results(results: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate independent component metrics once per candidate model."""
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_model[str(result["candidate_model"])].append(result)

    summaries = []
    for model in sorted(by_model):
        rows = by_model[model]
        cosine = _numbers(
            _metric(row, "cosine_similarity").get("score") for row in rows
        )
        bertscore = {
            component: _numbers(
                _metric(row, "bertscore").get(component) for row in rows
            )
            for component in ("precision", "recall", "f1")
        }
        latencies = {
            stage: _numbers(_mapping(row.get("latency_ms")).get(stage) for row in rows)
            for stage in LATENCY_STAGES
        }
        judge_scores = {
            criterion: _numbers(_judge_score(row, criterion) for row in rows)
            for criterion in JUDGE_CRITERIA
        }
        verdicts = Counter(
            verdict
            for row in rows
            if isinstance(
                verdict := _judgment(row).get("verdict"),
                str,
            )
        )

        summary: dict[str, Any] = {
            "candidate_model": model,
            "candidate_model_digest": rows[0].get("candidate_model_digest"),
            "evaluated_questions": len(rows),
            "successful_answers": sum(
                isinstance(answer := row.get("generated_answer"), str)
                and bool(answer.strip())
                for row in rows
            ),
            "failed_or_skipped": sum(
                bool(row.get("errors"))
                or not (
                    isinstance(answer := row.get("generated_answer"), str)
                    and bool(answer.strip())
                )
                for row in rows
            ),
            "cosine_count": len(cosine),
            "cosine_mean": _mean(cosine),
            "cosine_median": _median(cosine),
            "cosine_pass_rate": _rate(_bool_values(rows, "cosine_similarity")),
            "bertscore_count": len(bertscore["f1"]),
            "bertscore_precision_mean": _mean(bertscore["precision"]),
            "bertscore_recall_mean": _mean(bertscore["recall"]),
            "bertscore_f1_mean": _mean(bertscore["f1"]),
            "bertscore_f1_median": _median(bertscore["f1"]),
            "bertscore_pass_rate": _rate(_bool_values(rows, "bertscore")),
            "judge_count": len(judge_scores["correctness"]),
            "judge_correctness_mean": _mean(judge_scores["correctness"]),
            "judge_completeness_mean": _mean(judge_scores["completeness"]),
            "judge_faithfulness_mean": _mean(judge_scores["faithfulness"]),
            "judge_relevance_mean": _mean(judge_scores["relevance"]),
            "judge_pass_rate": verdicts["pass"] / sum(verdicts.values())
            if verdicts
            else None,
            "judge_partial_rate": verdicts["partial"] / sum(verdicts.values())
            if verdicts
            else None,
            "judge_fail_rate": verdicts["fail"] / sum(verdicts.values())
            if verdicts
            else None,
        }
        for stage, values in latencies.items():
            summary[f"{stage}_latency_mean_ms"] = _mean(values)
            summary[f"{stage}_latency_median_ms"] = _median(values)
        summaries.append(summary)
    return summaries


def write_summary_csv(path: Path, summaries: Sequence[dict[str, Any]]) -> None:
    """Write a flat instructor-friendly per-model summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(summaries[0]) if summaries else ["candidate_model"]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(_clean_csv_row(summary) for summary in summaries)


def _json_cell(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip trailing whitespace from each physical line in every string cell."""
    return {
        key: TRAILING_CSV_WHITESPACE.sub("", value)
        if isinstance(value, str)
        else value
        for key, value in row.items()
    }


def _criterion_field(
    judgment: dict[str, Any],
    criterion: str,
    field: str,
) -> Any:
    return _mapping(judgment.get(criterion)).get(field)


def _flatten_result(result: dict[str, Any]) -> dict[str, Any]:
    cosine = _metric(result, "cosine_similarity")
    bertscore = _metric(result, "bertscore")
    judge = _metric(result, "llm_judge")
    judgment = _mapping(judge.get("judgment"))
    latency = _mapping(result.get("latency_ms"))
    return {
        "schema_version": result.get("schema_version"),
        "run_id": result.get("run_id"),
        "dataset_version": result.get("dataset_version"),
        "question_id": result.get("question_id"),
        "question": result.get("question"),
        "candidate_model": result.get("candidate_model"),
        "candidate_model_digest": result.get("candidate_model_digest"),
        "generation_config": _json_cell(result.get("generation_config")),
        "rewritten_query": result.get("rewritten_query"),
        "generated_answer": result.get("generated_answer"),
        "reference_answer": result.get("reference_answer"),
        "reference_answers": _json_cell(result.get("reference_answers")),
        "gold_claims": _json_cell(result.get("gold_claims")),
        "gold_evidence": _json_cell(result.get("gold_evidence")),
        "cosine_score": cosine.get("score"),
        "cosine_threshold": cosine.get("threshold"),
        "cosine_passed": cosine.get("passed"),
        "cosine_selected_reference": cosine.get("selected_reference"),
        "cosine_selected_reference_index": cosine.get("selected_reference_index"),
        "bertscore_precision": bertscore.get("precision"),
        "bertscore_recall": bertscore.get("recall"),
        "bertscore_f1": bertscore.get("f1"),
        "bertscore_threshold": bertscore.get("threshold"),
        "bertscore_passed": bertscore.get("passed"),
        "bertscore_selected_reference": bertscore.get("selected_reference"),
        "bertscore_selected_reference_index": bertscore.get(
            "selected_reference_index"
        ),
        "judge_provider": judge.get("provider"),
        "judge_model": judge.get("model"),
        "judge_prompt_version": judge.get("prompt_version"),
        "judge_prompt_hash": judge.get("prompt_hash"),
        "judge_cache_key": judge.get("cache_key"),
        "judge_cache_hit": judge.get("cache_hit"),
        "judge_correctness_score": _criterion_field(
            judgment, "correctness", "score"
        ),
        "judge_correctness_justification": _criterion_field(
            judgment, "correctness", "justification"
        ),
        "judge_completeness_score": _criterion_field(
            judgment, "completeness", "score"
        ),
        "judge_completeness_justification": _criterion_field(
            judgment, "completeness", "justification"
        ),
        "judge_missing_claim_ids": _json_cell(
            _criterion_field(judgment, "completeness", "missing_claim_ids")
        ),
        "judge_faithfulness_score": _criterion_field(
            judgment, "faithfulness", "score"
        ),
        "judge_faithfulness_justification": _criterion_field(
            judgment, "faithfulness", "justification"
        ),
        "judge_unsupported_claims": _json_cell(
            _criterion_field(judgment, "faithfulness", "unsupported_claims")
        ),
        "judge_contradicted_claims": _json_cell(
            _criterion_field(judgment, "faithfulness", "contradicted_claims")
        ),
        "judge_relevance_score": _criterion_field(judgment, "relevance", "score"),
        "judge_relevance_justification": _criterion_field(
            judgment, "relevance", "justification"
        ),
        "judge_verdict": judgment.get("verdict"),
        **{
            f"{stage}_latency_ms": latency.get(stage)
            for stage in LATENCY_STAGES
        },
        "errors": _json_cell(result.get("errors")),
    }


def write_results_csv(
    path: Path,
    results: Sequence[dict[str, Any]],
) -> None:
    """Write audit-ready question-level results without retrieved or raw judge data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=RESULT_CSV_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(
            _clean_csv_row(_flatten_result(result)) for result in results
        )


def _format_number(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def classify_result_errors(result: dict[str, Any]) -> list[str]:
    """Return concise diagnostic labels without collapsing component scores."""
    labels = []
    judgment = _judgment(result)

    if _mapping(judgment.get("completeness")).get("missing_claim_ids"):
        labels.append("missing gold claim")
    if _mapping(judgment.get("faithfulness")).get("unsupported_claims"):
        labels.append("unsupported claim")
    if _mapping(judgment.get("faithfulness")).get("contradicted_claims"):
        labels.append("contradiction")
    labels.extend(
        f"{error.get('stage', 'pipeline')} failure"
        for error in result.get("errors", [])
        if isinstance(error, dict)
    )
    return list(dict.fromkeys(labels))


def _config_value(
    config: dict[str, Any],
    key: str,
    nested_key: str | None = None,
) -> Any:
    if key in config:
        return config[key]
    bertscore_config = _mapping(config.get("bertscore_config"))
    return bertscore_config.get(nested_key or key)


def _format_config_value(value: Any) -> str:
    if value is None:
        return "not recorded"
    if isinstance(value, (dict, list)):
        return _json_cell(value)
    return str(value)


def _markdown_text(value: Any) -> str:
    return _format_config_value(value).replace("|", "\\|").replace("\n", " ")


def write_markdown_report(
    path: Path,
    config: dict[str, Any],
    results: Sequence[dict[str, Any]],
    summaries: Sequence[dict[str, Any]],
) -> None:
    """Write configuration, independent metrics, latency, and diagnostics."""
    models = config.get("models")
    if not isinstance(models, list):
        models = [summary["candidate_model"] for summary in summaries]
    corpus_identity = _mapping(config.get("corpus_identity"))
    corpus_documents = corpus_identity.get("documents")
    if not isinstance(corpus_documents, list):
        corpus_documents = []
    corpus_lines = [
        (
            f"- Corpus manifest: "
            f"`{_markdown_text(corpus_identity.get('manifest_path'))}`; SHA-256 "
            f"`{_markdown_text(corpus_identity.get('manifest_hash'))}`; version "
            f"`{_markdown_text(corpus_identity.get('manifest_version'))}`; documents "
            f"`{_markdown_text(corpus_identity.get('document_count'))}`; indexed chunks "
            f"`{_markdown_text(corpus_identity.get('indexed_chunk_count'))}`"
        )
    ]
    for document in corpus_documents:
        identity = _mapping(document)
        corpus_lines.append(
            f"- Corpus document: `{_markdown_text(identity.get('document_path'))}`; "
            f"SHA-256 `{_markdown_text(identity.get('sha256'))}`; pages "
            f"`{_markdown_text(identity.get('page_count'))}`; indexed chunks "
            f"`{_markdown_text(identity.get('indexed_chunk_count'))}`"
        )
    bertscore_model = _config_value(config, "bertscore_model", "model")
    bertscore_revision = _config_value(
        config,
        "bertscore_model_revision",
        "model_revision",
    )
    bertscore_layers = _config_value(config, "bertscore_num_layers", "num_layers")
    bertscore_device = _config_value(config, "bertscore_device", "device")
    bertscore_idf = _config_value(config, "bertscore_idf", "idf")
    bertscore_rescaling = _config_value(
        config,
        "bertscore_rescale_with_baseline",
        "rescale_with_baseline",
    )
    bertscore_hash = _config_value(config, "bertscore_scorer_hash", "scorer_hash")
    bertscore_package = _config_value(config, "bertscore_package", "package")
    bertscore_version = _config_value(
        config,
        "bertscore_package_version",
        "package_version",
    )
    question_limit = config.get("question_limit")
    question_scope = "all" if question_limit is None else question_limit
    lines = [
        "# RAG Evaluation Report",
        "",
        "## Configuration",
        "",
        f"- Result contract: v{_markdown_text(config.get('schema_version'))}",
        (
            f"- Run: `{_markdown_text(config.get('run_id'))}`; created "
            f"`{_markdown_text(config.get('created_at'))}`"
        ),
        (
            f"- Dataset: `{_markdown_text(config.get('dataset_path'))}`; SHA-256 "
            f"`{_markdown_text(config.get('dataset_hash'))}`; version "
            f"`{_markdown_text(config.get('dataset_version'))}`; review status "
            f"`{_markdown_text(config.get('dataset_review_status'))}`; "
            f"{len(results)} result rows"
        ),
        *corpus_lines,
        (
            f"- Candidate models: `{_markdown_text(models)}`; digests "
            f"`{_markdown_text(config.get('model_digests'))}`"
        ),
        (
            f"- Embedding model: `{_markdown_text(config.get('embedding_model'))}`; "
            f"digest `{_markdown_text(config.get('embedding_model_digest'))}`"
        ),
        (
            f"- Generation settings: "
            f"`{_markdown_text(config.get('generation_config'))}`"
        ),
        (
            f"- Retrieval settings: "
            f"`{_markdown_text(config.get('retrieval_config'))}`"
        ),
        (
            f"- Question limit: `{_markdown_text(question_scope)}`; "
            f"metrics `{_markdown_text(config.get('metrics'))}`"
        ),
        (
            "- Cosine similarity: threshold "
            f"`{_markdown_text(config.get('cosine_threshold'))}`"
        ),
        (
            "- BERTScore: threshold "
            f"`{_markdown_text(config.get('bert_threshold'))}`, raw precision/recall/F1"
        ),
        (
            "- BERTScore scorer: "
            f"`{_markdown_text(bertscore_model)}`, revision "
            f"`{_markdown_text(bertscore_revision)}`, layer "
            f"`{_markdown_text(bertscore_layers)}`, device "
            f"`{_markdown_text(bertscore_device)}`, IDF "
            f"`{_markdown_text(bertscore_idf)}`, baseline rescaling "
            f"`{_markdown_text(bertscore_rescaling)}`, scorer hash "
            f"`{_markdown_text(bertscore_hash)}`, package "
            f"`{_markdown_text(bertscore_package)}` "
            f"`{_markdown_text(bertscore_version)}`"
        ),
        (
            f"- LLM judge: enabled `{_markdown_text(config.get('judge_enabled'))}`; "
            f"provider `{_markdown_text(config.get('judge_provider'))}`; model "
            f"`{_markdown_text(config.get('judge_model'))}`; temperature "
            f"`{_markdown_text(config.get('judge_temperature'))}`; request policy "
            f"`{_markdown_text(config.get('judge_request_policy'))}`; cache bypassed "
            f"`{_markdown_text(config.get('judge_cache_bypassed'))}`"
        ),
        "",
        "Cosine similarity, BERTScore, and the LLM judge are reported independently. "
        "**No combined score or overall pass is calculated.**",
        "",
        "## Answer similarity",
        "",
        "| Model | Rows | Cos N | Cosine mean | Cosine median | Cosine pass | "
        "BERT N | BERT P | BERT R | BERT F1 | BERT F1 median | BERT pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        cells = [
            summary["candidate_model"],
            summary["evaluated_questions"],
            summary["cosine_count"],
            summary["cosine_mean"],
            summary["cosine_median"],
            summary["cosine_pass_rate"],
            summary["bertscore_count"],
            summary["bertscore_precision_mean"],
            summary["bertscore_recall_mean"],
            summary["bertscore_f1_mean"],
            summary["bertscore_f1_median"],
            summary["bertscore_pass_rate"],
        ]
        lines.append("| " + " | ".join(_format_number(value) for value in cells) + " |")

    lines.extend(
        [
            "",
            "## LLM judge",
            "",
            "| Model | N | Correct | Complete | Faithful | Relevant | Pass | "
            "Partial | Fail |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in summaries:
        cells = [
            summary["candidate_model"],
            summary["judge_count"],
            summary["judge_correctness_mean"],
            summary["judge_completeness_mean"],
            summary["judge_faithfulness_mean"],
            summary["judge_relevance_mean"],
            summary["judge_pass_rate"],
            summary["judge_partial_rate"],
            summary["judge_fail_rate"],
        ]
        lines.append("| " + " | ".join(_format_number(value) for value in cells) + " |")

    lines.extend(
        [
            "",
            "## Latency and technical failures",
            "",
            "| Model | Rewrite ms | Retrieval ms | Generation ms | Judge ms | "
            "Total ms | Total median ms | Errors |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in summaries:
        cells = [
            summary["candidate_model"],
            summary["rewrite_latency_mean_ms"],
            summary["retrieval_latency_mean_ms"],
            summary["generation_latency_mean_ms"],
            summary["judge_latency_mean_ms"],
            summary["total_latency_mean_ms"],
            summary["total_latency_median_ms"],
            summary["failed_or_skipped"],
        ]
        lines.append("| " + " | ".join(_format_number(value) for value in cells) + " |")

    errors = [
        (result, labels)
        for result in results
        if (labels := classify_result_errors(result))
    ]
    lines.extend(
        [
            "",
            "## Question-level diagnostics",
            "",
            "| Question | Model | Diagnostics |",
            "|---|---|---|",
        ]
    )
    if errors:
        for result, labels in errors:
            lines.append(
                f"| `{result['question_id']}` | `{result['candidate_model']}` | "
                f"{_markdown_text('; '.join(labels))} |"
            )
    else:
        lines.append("| - | - | No failures detected |")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Cosine similarity measures embedding agreement with an accepted reference; "
            "it does not prove factual correctness.",
            "- BERTScore reports raw token-level semantic precision, recall, and F1. Its "
            "pass decision uses F1 only.",
            "- The LLM judge is a consistent rubric-based aid, not a substitute for expert "
            "human review.",
            "- Metric pass rates are independent and must not be interpreted as a combined "
            "or overall result.",
            "- Each pass rate uses only rows where that metric returned a pass decision; "
            "metric counts and technical failures show missing results.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manual_review(
    path: Path,
    results: Sequence[dict[str, Any]],
    *,
    limit: int = MANUAL_REVIEW_LIMIT,
) -> None:
    """Export a deterministic result subset with blank human-label fields."""
    sample_size = min(limit, len(results))
    indices = sorted(
        random.Random(MANUAL_REVIEW_SEED).sample(range(len(results)), sample_size)
    )
    review_rows = []
    for index in indices:
        result = results[index]
        review_rows.append(
            {
                "question_id": result["question_id"],
                "question": result["question"],
                "gold_answer": result["reference_answer"],
                "gold_claims": result["gold_claims"],
                "gold_evidence": result["gold_evidence"],
                "retrieved_context": [
                    chunk for chunk in result["retrieved_chunks"] if chunk["used_for_generation"]
                ],
                "candidate_model": result["candidate_model"],
                "candidate_answer": result["generated_answer"],
                "human_correctness": None,
                "human_completeness": None,
                "human_faithfulness": None,
                "notes": None,
            }
        )
    payload = {
        "seed": MANUAL_REVIEW_SEED,
        "sample_size": sample_size,
        "instructions": (
            "Label correctness, completeness, and faithfulness as pass, partial, or fail."
        ),
        "records": review_rows,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_reports(
    run_dir: Path,
    config: dict[str, Any],
    results: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Write every derived report from persisted question-level results."""
    summaries = summarize_results(results)
    write_results_csv(run_dir / "results.csv", results)
    write_summary_csv(run_dir / "summary.csv", summaries)
    write_markdown_report(run_dir / "report.md", config, results, summaries)
    write_manual_review(run_dir / "manual_review.json", results)
    return summaries
