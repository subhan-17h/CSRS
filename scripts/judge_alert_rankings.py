#!/usr/bin/env python3
# ruff: noqa: E501  (the prompt block below is verbatim contract text; see module docstring)

"""Score the local models' severity rankings with a Groq-hosted GPT-OSS judge.

For every parsed (model, alert) row in the RAG ranking snapshot
(alert_rag_run.jsonl), the Groq judge (openai/gpt-oss-120b) receives the local
model's output (rank, justification, metrics_used), the COMPLETE original
Snort alert (header plus full rule documentation) and the ground truth (Snort
priority mapped to its 1-5 anchor). It returns a strict JSON verdict with a
correctness score on 0-1:

    1.0        rank exactly matches the anchored ground truth
    0.5-0.9    rank is within one step of the anchored ground truth
    0.0-0.4    rank is more than one step away

Within each band the judge may raise the score for a coherent, evidence-based
justification and lower it for one that misreads the record.

The judge SEES the ground truth: this is an agreement check, not a blind
plausibility review. Transport retries, backoff and daily-quota detection
mirror eval/judge.py (imported from there); the verdict schema is this
script's own. A shared free-tier rate limiter paces requests and persists
daily usage. Each (model, alert) row is upserted into a resumable JSONL
snapshot; --resume skips complete rows. A daily-quota stop exits with code 2
and resumes with --resume after the quota resets. GROQ_API_KEY is read from
CSRS/.env.

Usage:
    uv run python scripts/judge_alert_rankings.py [--models M1 M2] [--resume]
        [--rpm N] [--rpd N] [--tpm N] [--tpd N] [--budget-file PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import groq_llm
from csrs.alert_ranking import anchored_rank, is_mismatch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CIL_ROOT = PROJECT_ROOT.parent
DEFAULT_RUN = CIL_ROOT / "alert_rag_run.jsonl"
DEFAULT_SAMPLE = CIL_ROOT / "alert_sample_50.json"
DEFAULT_RESULTS = CIL_ROOT / "alert_judge_run.jsonl"
DEFAULT_MODELS = ("openai/gpt-oss-120b",)

# Reuse the eval judge's transport plumbing: settings loader, error taxonomy,
# retry budget, backoff and quota detection live in eval/judge.py.
sys.path.insert(0, str(PROJECT_ROOT / "eval"))
from judge import (  # noqa: E402  (deliberate: sibling eval module)
    MAX_REQUEST_ATTEMPTS,
    GroqJudge,
    JudgeConfigurationError,
    JudgeQuotaError,
    JudgeRequestError,
    JudgeResponseError,
    load_judge_settings,
)

JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_PROMPT_VERSION = "severity_judge_v1"
TEMPERATURE = 0
MAX_COMPLETION_TOKENS = 1_200
REASONING_EFFORT = "low"
INCLUDE_REASONING = False
QUOTA_ERROR_MESSAGE = (
    "Groq judge daily token quota was exhausted; resume this run after the quota resets"
)

SYSTEM = """You are an expert severity-ranking judge.

A local LLM ranked ONE Snort alert on a 1-5 severity scale (1 = MOST severe, 5 = least
severe). You receive the local model's output - its rank, its justification, and the
record fields it says it weighed - plus the COMPLETE original Snort alert: the alert
header and the full rule documentation. Snort's own priority (a coarser 1-3 scale, 1 =
most severe) is included and is mapped to the model's 5-point scale as the
ground-truth anchor: Snort 1 -> rank 1, Snort 2 -> rank 3, Snort 3 -> rank 5.

Score how correct the local model's rank decision was, on a 0-1 scale:
- 1.0: rank exactly equals the anchored ground-truth rank.
- 0.5-0.9: rank is within ONE step of the anchored ground-truth rank (|rank - anchored| = 1).
- 0.0-0.4: rank differs by MORE than one step (|rank - anchored| > 1).

Within each band, raise the score when the model's justification is coherent and
grounded in the record; lower it when the justification misreads the record, invents
values, or ignores stronger evidence.

Rules:
- Judge the rank decision, not the prose. Rank distance decides the band first; the
  justification only nudges the score within that band.
- Do not invent alert facts. Evaluate only the material you receive.
- Respond with a single JSON object matching the supplied schema:
  {"score": float in [0,1], "reasoning": string}. The reasoning is 1-3 sentences
  stating the model's rank, the anchored ground truth, and why the score was assigned,
  citing justification issues when they affected the score."""


class SeverityJudgment(BaseModel):
    """Strict structured verdict produced by the fixed Groq severity judge."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=1)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


class _RequestBudget:
    """Shared transport-call budget across initial and repair requests."""

    attempts: int = 0
    transient_failures: int = 0
    daily_quota_seen: bool = False


def _client_from_env() -> Any:
    settings = load_judge_settings(PROJECT_ROOT / ".env")
    if settings.api_key is None or not settings.api_key.get_secret_value().strip():
        raise JudgeConfigurationError(
            "GROQ_API_KEY is required; set it in CSRS/.env"
        )
    try:
        from groq import Groq
    except ImportError as error:
        raise JudgeConfigurationError(
            "Groq evaluation dependency is missing; install the eval dependency group"
        ) from error
    return Groq(api_key=settings.api_key.get_secret_value(), max_retries=0)


def _request(client: Any, messages: list[dict[str, str]],
             budget: _RequestBudget,
             limiter: groq_llm.RateLimiter | None = None) -> tuple[str, str]:
    """Call Groq once with bounded retries; return (content, finish_reason)."""
    while budget.attempts < MAX_REQUEST_ATTEMPTS:
        budget.attempts += 1
        if limiter is not None:
            message_text = "".join(message["content"] for message in messages)
            estimated_input = (
                groq_llm.estimate_tokens(message_text) + MAX_COMPLETION_TOKENS
            )
            limiter.before_request(estimated_input, MAX_COMPLETION_TOKENS)
        try:
            response = client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=messages,
                temperature=TEMPERATURE,
                reasoning_effort=REASONING_EFFORT,
                include_reasoning=INCLUDE_REASONING,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "severity_judgment",
                        "strict": True,
                        "schema": SeverityJudgment.model_json_schema(),
                    },
                },
            )
        except Exception as error:
            if not GroqJudge._is_transient_error(error):
                raise JudgeRequestError(f"Groq judge request failed: {error}") from error
            budget.daily_quota_seen = (
                budget.daily_quota_seen or GroqJudge._is_daily_token_quota_error(error)
            )
            if budget.attempts == MAX_REQUEST_ATTEMPTS:
                if budget.daily_quota_seen:
                    raise JudgeQuotaError(QUOTA_ERROR_MESSAGE) from error
                raise JudgeRequestError(
                    f"Groq judge request failed after {MAX_REQUEST_ATTEMPTS} "
                    f"total attempts: {error}"
                ) from error
            if limiter is not None:
                limiter.note_error(error)
            delay = GroqJudge._retry_delay(error, budget.transient_failures)
            budget.transient_failures += 1
            time.sleep(delay)
            continue
        break
    else:
        raise JudgeRequestError(
            f"Groq judge exhausted {MAX_REQUEST_ATTEMPTS} total attempts "
            "before structured-output repair"
        )
    try:
        choice = response.choices[0]
        content = choice.message.content
    except (AttributeError, IndexError, TypeError) as error:
        raise JudgeResponseError("Groq judge response did not contain message content") from error
    if not isinstance(content, str) or not content.strip():
        raise JudgeResponseError("Groq judge response content was empty")
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    if limiter is not None:
        limiter.after_request(prompt_tokens, completion_tokens)
    return content, getattr(choice, "finish_reason", None)


def _parse_verdict(raw_response: str) -> SeverityJudgment:
    try:
        return SeverityJudgment.model_validate_json(raw_response)
    except ValidationError as error:
        raise JudgeResponseError(
            f"structured verdict failed validation: {error}"
        ) from error


def call_judge(client: Any, payload: dict[str, Any],
               limiter: groq_llm.RateLimiter | None = None
               ) -> tuple[str, SeverityJudgment | None, str | None, str | None]:
    """Judge one row: bounded transport retries, one repair retry, verbatim response."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _canonical_json(payload)},
    ]
    budget = _RequestBudget()
    raw_response, done_reason = _request(client, messages, budget, limiter)
    try:
        verdict = _parse_verdict(raw_response)
    except JudgeResponseError as first_error:
        repair_messages = [
            *messages,
            {"role": "assistant", "content": raw_response[:8_000]},
            {
                "role": "user",
                "content": (
                    "The previous response was invalid. Return only a corrected JSON "
                    "object that satisfies the supplied schema."
                ),
            },
        ]
        repaired_response, done_reason = _request(
            client, repair_messages, budget, limiter
        )
        try:
            verdict = _parse_verdict(repaired_response)
        except JudgeResponseError as second_error:
            raise JudgeResponseError(
                "Groq judge returned invalid structured output after one repair retry: "
                f"{second_error}"
            ) from first_error
        raw_response = repaired_response
    return raw_response, verdict, done_reason, None


def load_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_results_atomically(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def upsert_result(path: Path, rows: list[dict[str, Any]],
                  row: dict[str, Any]) -> None:
    key = (row["model"], row["alert_id"])
    updated = [existing for existing in rows
               if (existing["model"], existing["alert_id"]) != key]
    updated.append(row)
    write_results_atomically(path, updated)
    rows[:] = updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", default=str(DEFAULT_RUN))
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--resume", action="store_true",
                        help="skip (model, alert) rows already complete in --results")
    parser.add_argument("--rpm", type=int, default=groq_llm.DEFAULT_RPM)
    parser.add_argument("--rpd", type=int, default=groq_llm.DEFAULT_RPD)
    parser.add_argument("--tpm", type=int, default=groq_llm.DEFAULT_TPM)
    parser.add_argument("--tpd", type=int, default=groq_llm.DEFAULT_TPD)
    parser.add_argument("--budget-file", default=str(groq_llm.DEFAULT_TRACKER_PATH))
    args = parser.parse_args()

    run_rows = [json.loads(line) for line in Path(args.run).read_text(encoding="utf-8")
                .splitlines() if line.strip()]
    if not run_rows:
        sys.exit(f"no rows in {args.run} - run scripts/run_alert_rag.py first")
    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    by_id = {entry["alert_id"]: entry for entry in sample["entries"]}

    run_ids = {row["run_id"] for row in run_rows}
    assert len(run_ids) == 1, f"mixed run ids in snapshot: {sorted(run_ids)}"
    run_id = sorted(run_ids)[0]

    rows_by = {(row["model"], row["alert_id"]): row for row in run_rows}
    assert len(rows_by) == len(run_rows), "duplicate (model, alert) rows in snapshot"

    pending = []
    for row in run_rows:
        if row["model"] in args.models and row["status"] == "parsed":
            pending.append((row["model"], row["alert_id"]))
    missing = [model for model in args.models
               if not any(r["model"] == model for r in run_rows)]
    if missing:
        sys.exit(f"models {', '.join(missing)} have no rows in the run snapshot")

    client = _client_from_env()
    tracker = groq_llm.DailyUsageTracker(Path(args.budget_file))
    limiter = groq_llm.RateLimiter(
        rpm=args.rpm,
        rpd=args.rpd,
        tpm=args.tpm,
        tpd=args.tpd,
        tracker=tracker,
    )
    results_path = Path(args.results)
    results = load_results(results_path) if args.resume else []
    existing = {(row["model"], row["alert_id"]) for row in results
                if row["status"] == "parsed"}

    started = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for i, (model, alert_id) in enumerate(pending, start=1):
        if (model, alert_id) in existing:
            print(f"[{i:2d}/{len(pending)}] {alert_id} {model} already complete",
                  flush=True)
            continue
        run_row = rows_by[(model, alert_id)]
        entry = by_id[alert_id]
        priority = int(entry["alert"]["priority"])
        rank = run_row["parsed"]["rank"]
        anchored = anchored_rank(priority)
        payload = {
            "alert_id": alert_id,
            "candidate": {
                "model": model,
                "rank": rank,
                "justification": run_row["parsed"]["justification"],
                "metrics_used": run_row["parsed"]["metrics_used"],
            },
            "ground_truth": {
                "snort_priority": priority,
                "anchored_rank": anchored,
            },
            "alert": entry,
        }
        t1 = time.monotonic()
        try:
            raw_response, verdict, done_reason, error = call_judge(
                client, payload, limiter
            )
            status = "parsed" if verdict is not None else "failed"
        except groq_llm.GroqQuotaStop as error:
            print(error)
            return 2
        except JudgeQuotaError as error:
            print(error)
            return 2
        except (JudgeRequestError, JudgeResponseError) as error:
            verdict = None
            done_reason = None
            raw_response = ""
            status = "failed"
            print(f"[{i:2d}/{len(pending)}] {alert_id} {model} ERROR: {error}",
                  flush=True)
        latency_ms = (time.monotonic() - t1) * 1000
        row = {
            "schema_version": 1,
            "run_id": run_id,
            "judged_at": started,
            "judge_model": JUDGE_MODEL,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "model": model,
            "alert_id": alert_id,
            "rule_id": run_row.get("rule_id"),
            "snort_priority": priority,
            "anchored_rank": anchored,
            "llm_rank": rank,
            "mismatch": is_mismatch(rank, priority),
            "prompt": payload,
            "response": raw_response,
            "verdict": verdict.model_dump(mode="json") if verdict else None,
            "status": status,
            "done_reason": done_reason,
            "error": str(error) if error else None,
            "latency_ms": round(latency_ms),
        }
        upsert_result(results_path, results, row)
        existing.add((model, alert_id))
        score = f"{verdict.score:.2f}" if verdict else "FAILED"
        print(f"[{i:2d}/{len(pending)}] {alert_id} {model} "
              f"rank {rank} vs anchored {anchored} -> judge {score}", flush=True)

    parsed = [row for row in results if row["status"] == "parsed"]
    print(f"\njudged {len(parsed)}/{len(pending)} parsed rankings "
          f"(snapshot has {len(results)} rows)")
    if len(parsed) != len(pending):
        print("FAILED ROWS:")
        for row in results:
            if row["status"] != "parsed":
                print(f"  alert {row['alert_id']} {row['model']}: {row.get('error')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
