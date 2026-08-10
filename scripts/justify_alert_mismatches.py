#!/usr/bin/env python3
# ruff: noqa: E501  (the prompt block below is verbatim contract text; see module docstring)

"""Ask each local model to justify its severity-rank mismatches.

For every (model, alert) row in the RAG ranking snapshot
(alert_rag_run.jsonl) whose rank is a mismatch against the anchored Snort
ground truth (|rank - ANCHOR[priority]| > 1, ANCHOR = {1:1, 2:3, 3:5}), the
model is re-queried with its OWN original evidence ([S1]..[S5] chunks stored
in the run row), its recorded rank and justification, and the Snort ground
truth, and asked to explain (a) why its rank differs from the ground truth and
(b) what evidence led to its rank. Existing rankings are untouched.

The pass reuses each run row's stored chunks - no retrieval is performed
again, and no re-ranking happens. Same Ollama contract as the ranking run
(temperature 0, seed 42, num_ctx 8192, repeat_penalty 1.15, num_predict 300),
one retry on an empty answer, both attempts recorded verbatim, never coerced.
Each (model, alert) row is upserted into a resumable JSONL snapshot;
--resume skips complete rows.

Usage:
    uv run python scripts/justify_alert_mismatches.py [--models M1 M2] [--resume]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ollama

from csrs.alert_ranking import anchored_rank, is_mismatch
from csrs.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CIL_ROOT = PROJECT_ROOT.parent
DEFAULT_RUN = CIL_ROOT / "alert_rag_run.jsonl"
DEFAULT_SAMPLE = CIL_ROOT / "alert_sample_50.json"
DEFAULT_RESULTS = CIL_ROOT / "alert_mismatch_justifications.jsonl"
DEFAULT_MODELS = ("llama3.2:latest", "gemma2:2b")

OPTIONS = {
    "temperature": 0,
    "seed": 42,
    "num_ctx": 8192,
    "repeat_penalty": 1.15,
    "num_predict": 300,
}

SYSTEM = """You are a senior SOC analyst explaining a previous severity-ranking decision.

Earlier you ranked a Snort alert on a 1-5 severity scale (1 = MOST severe, 5 = least
severe). That rank was compared with the alert's own Snort ground-truth priority,
mapped to the same 5-point scale (Snort 1 -> rank 1, Snort 2 -> rank 3, Snort 3 ->
rank 5). Your rank differs from that ground-truth rank by more than one scale step.

Your task now is ONLY to explain that decision. Do not change your rank, do not
re-rank the alert, do not assign a new rank.

Explain in 2-4 plain sentences:
1. Why your rank differs from the Snort ground-truth rank - what you weighed
   differently than Snort's priority suggests.
2. What specific evidence in the alert record and in the [S1]..[S5] standards
   context led you to the rank you assigned.

Rules:
- You are explaining a past decision, not making a new one; never state a rank.
- Cite only evidence that actually appears in the alert record or in the standards
  context shown to you. Never invent fields, CVEs or scores.
- Reply with your explanation only: 2-4 plain sentences, no preamble, no bullets,
  no rank, no format markers."""

RETRY_REMINDER = """Your previous answer was empty or off-task. Reply again with your explanation only:
2-4 plain sentences, no preamble, no bullets, no rank, no format markers."""


def build_user_message(entry: dict[str, Any], chunks: list[dict[str, Any]],
                       rank: int, anchored: int, priority: int) -> str:
    """Ground-truth block plus the model's own evidence and rank, no re-ranking."""
    context = "\n\n".join(
        f"[S{position}]\n{chunk['text']}\n[/S{position}]"
        for position, chunk in enumerate(chunks, start=1)
    )
    alert_json = json.dumps(entry, indent=2)
    return (
        "CONTEXT - your original retrieved standards evidence\n"
        f"{context}\n\n"
        f"ALERT RECORD\n{alert_json}\n\n"
        "YOUR PREVIOUS DECISION\n"
        f"Rank: {rank} (1-5 scale, 1 = MOST severe)\n\n"
        "SNORT GROUND TRUTH\n"
        f"priority: {priority} (Snort's own 1-3 scale, 1 = most severe)\n"
        f"ground-truth rank on the 1-5 scale: {anchored}\n\n"
        "Your rank differs from the ground truth by more than one scale step.\n"
        "Explain in 2-4 plain sentences: (1) why your rank differs from the Snort "
        "ground-truth rank, and (2) what evidence in the alert record and standards "
        "context led you to your rank. Reply with your explanation only."
    )


def call_model(client: ollama.Client, model: str,
               user_message: str) -> tuple[list[dict[str, Any]], str, str | None]:
    """Call the model once, retry once, and record both attempts verbatim."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_message},
    ]
    attempts: list[dict[str, Any]] = []
    justification: str | None = None
    for _ in range(2):
        response = client.chat(
            model=model,
            messages=messages,
            options=OPTIONS,
            keep_alive=settings.keep_alive,
        )
        content = response["message"]["content"].strip()
        meta = {
            "done_reason": response.get("done_reason"),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "eval_count": response.get("eval_count"),
            "total_duration": response.get("total_duration"),
        }
        attempts.append({"content": content, "meta": meta})
        if content:
            justification = content
            break
        messages.append({"role": "user", "content": RETRY_REMINDER})
    status = "parsed" if justification is not None else "failed"
    return attempts, status, justification


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
    args = parser.parse_args()

    run_rows = [json.loads(line) for line in Path(args.run).read_text(encoding="utf-8")
                .splitlines() if line.strip()]
    if not run_rows:
        sys.exit(f"no rows in {args.run} - run scripts/run_alert_rag.py first")
    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    by_id = {entry["alert_id"]: entry for entry in sample["entries"]}

    run_ids = {row["run_id"] for row in run_rows}
    assert len(run_ids) == 1, f"mixed run ids in snapshot: {sorted(run_ids)}"

    rows_by = {(row["model"], row["alert_id"]): row for row in run_rows}
    assert len(rows_by) == len(run_rows), "duplicate (model, alert) rows in snapshot"

    # Mismatch rows for the requested models, preserving run order.
    pending_pairs = []
    for row in run_rows:
        if row["model"] not in args.models or row["status"] != "parsed":
            continue
        priority = int(by_id[row["alert_id"]]["alert"]["priority"])
        if is_mismatch(row["parsed"]["rank"], priority):
            pending_pairs.append((row["model"], row["alert_id"]))
    missing = [model for model in args.models
               if not any(r["model"] == model for r in run_rows)]
    if missing:
        sys.exit(f"models {', '.join(missing)} have no rows in the run snapshot")

    client = ollama.Client(host=settings.ollama_host)
    results_path = Path(args.results)
    results = load_results(results_path) if args.resume else []
    existing = {(row["model"], row["alert_id"]) for row in results
                if row["status"] == "parsed"}

    started = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for i, (model, alert_id) in enumerate(pending_pairs, start=1):
        if (model, alert_id) in existing:
            print(f"[{i:2d}/{len(pending_pairs)}] {alert_id} {model} already complete",
                  flush=True)
            continue
        run_row = rows_by[(model, alert_id)]
        entry = by_id[alert_id]
        priority = int(entry["alert"]["priority"])
        rank = run_row["parsed"]["rank"]
        anchored = anchored_rank(priority)
        user_message = build_user_message(entry, run_row["chunks"], rank, anchored, priority)
        t1 = time.monotonic()
        attempts, status, justification = call_model(client, model, user_message)
        generation_ms = (time.monotonic() - t1) * 1000
        row = {
            "schema_version": 1,
            "run_id": run_row["run_id"],
            "justified_at": started,
            "model": model,
            "alert_id": alert_id,
            "rule_id": run_row.get("rule_id"),
            "snort_priority": priority,
            "anchored_rank": anchored,
            "llm_rank": rank,
            "mismatch": True,
            "justification": justification,
            "attempts": attempts,
            "status": status,
            "done_reasons": [attempt["meta"].get("done_reason") for attempt in attempts],
            "latency_ms": {"generation": round(generation_ms)},
        }
        upsert_result(results_path, results, row)
        existing.add((model, alert_id))
        print(f"[{i:2d}/{len(pending_pairs)}] {alert_id} {model} "
              f"rank {rank} vs anchored {anchored} -> "
              f"{'ok' if status == 'parsed' else 'FAILED'}  "
              f"{(justification or '(empty)')[:80]}", flush=True)

    parsed = [row for row in results if row["status"] == "parsed"]
    print(f"\njustified {len(parsed)}/{len(pending_pairs)} mismatch rows "
          f"(snapshot has {len(results)} rows)")
    if len(parsed) != len(pending_pairs):
        print("FAILED ROWS:")
        for row in results:
            if row["status"] != "parsed":
                for attempt in row["attempts"]:
                    print(f"  alert {row['alert_id']} {row['model']} "
                          f"attempt: {attempt['content'][:160]!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
