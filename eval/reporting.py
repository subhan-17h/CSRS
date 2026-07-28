"""Small JSONL, CSV, Markdown, and manual-review outputs for evaluation runs."""

from __future__ import annotations

import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

MANUAL_REVIEW_SEED = 42
MANUAL_REVIEW_LIMIT = 30


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


def _judge_score(result: dict[str, Any], criterion: str) -> int | None:
    judge = result.get("metrics", {}).get("llm_judge")
    if not isinstance(judge, dict):
        return None
    judgment = judge.get("judgment")
    if not isinstance(judgment, dict):
        return None
    criterion_value = judgment.get(criterion)
    if not isinstance(criterion_value, dict):
        return None
    score = criterion_value.get("score")
    return score if isinstance(score, int) and not isinstance(score, bool) else None


def _judgment(result: dict[str, Any]) -> dict[str, Any]:
    judge = result.get("metrics", {}).get("llm_judge")
    if not isinstance(judge, dict):
        return {}
    judgment = judge.get("judgment")
    return judgment if isinstance(judgment, dict) else {}


def summarize_results(results: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate independent component metrics once per candidate model."""
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_model[str(result["candidate_model"])].append(result)

    summaries = []
    for model in sorted(by_model):
        rows = by_model[model]
        cosine = _numbers(
            row.get("metrics", {}).get("cosine_similarity", {}).get("score")
            for row in rows
        )
        cosine_passes = [
            value
            for row in rows
            if isinstance(
                value := row.get("metrics", {})
                .get("cosine_similarity", {})
                .get("passed"),
                bool,
            )
        ]
        generation_latency = _numbers(
            row.get("latency_ms", {}).get("generation") for row in rows
        )
        judge_scores = {
            criterion: _numbers(_judge_score(row, criterion) for row in rows)
            for criterion in ("correctness", "completeness", "faithfulness", "relevance")
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
                isinstance(row.get("generated_answer"), str) for row in rows
            ),
            "failed_or_skipped": sum(bool(row.get("errors")) for row in rows),
            "cosine_count": len(cosine),
            "cosine_mean": _mean(cosine),
            "cosine_median": _median(cosine),
            "cosine_pass_rate": _rate(cosine_passes),
            "generation_latency_mean_ms": _mean(generation_latency),
            "generation_latency_median_ms": _median(generation_latency),
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
        for depth in (5, 10):
            hits = [
                value
                for row in rows
                if isinstance(
                    value := row.get("metrics", {})
                    .get("retrieval_evidence", {})
                    .get(f"evidence_hit_at_{depth}"),
                    bool,
                )
            ]
            recalls = _numbers(
                row.get("metrics", {})
                .get("retrieval_evidence", {})
                .get(f"evidence_recall_at_{depth}")
                for row in rows
            )
            summary[f"evidence_hit_rate_at_{depth}"] = _rate(hits)
            summary[f"evidence_recall_at_{depth}"] = _mean(recalls)
        summaries.append(summary)
    return summaries


def write_summary_csv(path: Path, summaries: Sequence[dict[str, Any]]) -> None:
    """Write a flat instructor-friendly per-model summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(summaries[0]) if summaries else ["candidate_model"]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)


def _format_number(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def classify_result_errors(result: dict[str, Any]) -> list[str]:
    """Return concise diagnostic labels without collapsing component scores."""
    labels = []
    retrieval = result.get("metrics", {}).get("retrieval_evidence", {})
    judge = result.get("metrics", {}).get("llm_judge", {})
    judgment = judge.get("judgment", {}) if isinstance(judge, dict) else {}

    if retrieval.get("evidence_hit_at_5") is False:
        labels.append("retrieval miss")
    if (
        retrieval.get("evidence_hit_at_5") is True
        and judgment.get("correctness", {}).get("score", 4) <= 2
    ):
        labels.append("evidence retrieved; answer incorrect")
    if judgment.get("completeness", {}).get("missing_claim_ids"):
        labels.append("missing gold claim")
    if judgment.get("faithfulness", {}).get("unsupported_claims"):
        labels.append("unsupported claim")
    if judgment.get("faithfulness", {}).get("contradicted_claims"):
        labels.append("contradiction")
    labels.extend(
        f"{error.get('stage', 'pipeline')} failure"
        for error in result.get("errors", [])
        if isinstance(error, dict)
    )
    return list(dict.fromkeys(labels))


def write_markdown_report(
    path: Path,
    config: dict[str, Any],
    results: Sequence[dict[str, Any]],
    summaries: Sequence[dict[str, Any]],
) -> None:
    """Write a concise component-score report and question-level error table."""
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Run: `{config['run_id']}`",
        f"- Dataset: `{config['dataset_version']}` ({len(results)} result rows)",
        f"- Judge enabled: `{config['judge_enabled']}`",
        (
            "- Cosine threshold: "
            f"`{config['cosine_threshold']}` (provisional, not calibrated)"
        ),
        "",
        "No combined score is calculated. Cosine similarity does not prove factual "
        "correctness.",
        "",
        "## Per-model metrics",
        "",
        "| Model | N | Cosine mean | Cosine median | Cosine pass | Judge correct | "
        "Judge complete | Judge faithful | Judge pass | Hit@5 | Recall@5 | "
        "Hit@10 | Recall@10 | Gen ms | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        cells = [
            summary["candidate_model"],
            summary["evaluated_questions"],
            summary["cosine_mean"],
            summary["cosine_median"],
            summary["cosine_pass_rate"],
            summary["judge_correctness_mean"],
            summary["judge_completeness_mean"],
            summary["judge_faithfulness_mean"],
            summary["judge_pass_rate"],
            summary["evidence_hit_rate_at_5"],
            summary["evidence_recall_at_5"],
            summary["evidence_hit_rate_at_10"],
            summary["evidence_recall_at_10"],
            summary["generation_latency_mean_ms"],
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
                f"{'; '.join(labels)} |"
            )
    else:
        lines.append("| - | - | No failures detected |")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Cosine similarity measures semantic agreement with the reference answer; "
            "the 0.75 threshold is provisional.",
            "- Evidence hit/recall measures whether gold passages appeared in retrieval, "
            "not whether the answer used them correctly.",
            "- The LLM judge is a consistent rubric-based aid, not a substitute for expert "
            "human review.",
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
    write_summary_csv(run_dir / "summary.csv", summaries)
    write_markdown_report(run_dir / "report.md", config, results, summaries)
    write_manual_review(run_dir / "manual_review.json", results)
    return summaries
