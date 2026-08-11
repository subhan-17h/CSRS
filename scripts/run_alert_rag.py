#!/usr/bin/env python3
# ruff: noqa: E501  (the prompt blocks below are verbatim contract text; see module docstring)

"""Rank 50 Snort alerts grounded in retrieved cybersecurity-standards context.

For each alert in the sample, a deterministic query is composed from the
record (alert_message plus rule documentation fields, rule_documentation
weighted), embedded, and run through the CSRS hybrid retriever (Chroma dense
+ BM25, RRF-fused) against a corpus of three standards (NIST CSF 2.0,
ISO/IEC 27001:2022, NIST SP 800-53 Rev 5). The top chunks are injected into
the model prompt as [S1]..[S5] context alongside the full alert record, and
the Groq-hosted openai/gpt-oss-120b model ranks severity on a 1-5 scale
(1 = MOST severe, 5 = least) under the strict pipe contract:

    <rank 1-5> | <short 3-10 word justification> | <comma-separated field names>

One call per alert, fresh context every time: batched list-ranking failed
repeatedly on llama3.2 in earlier sessions (scrambled ids, positional rank
cycles, fabricated values). One retry per alert, both attempts recorded
verbatim, never coerced. Each (model, alert) row is upserted into a
resumable JSONL snapshot; --resume skips complete rows.

Usage:
    uv run python scripts/run_alert_rag.py [--limit N] [--models M1 M2]
                                           [--top-k K] [--resume]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ollama

import groq_llm
from csrs.config import settings
from csrs.embeddings import embed_query
from csrs.model_names import canonical_model_name
from csrs.models import RetrievedChunk
from csrs.pipeline import Pipeline
from csrs.retrieval import retrieve
from csrs.store import ChunkStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CIL_ROOT = PROJECT_ROOT.parent
DEFAULT_SAMPLE = CIL_ROOT / "alert_sample_50.json"
DEFAULT_RESULTS = CIL_ROOT / "alert_rag_run.jsonl"
DEFAULT_MODELS = ("openai/gpt-oss-120b",)

CONTRACT = "pipe"
RETRIEVAL_LIMIT = 5
RETRIEVAL_LIMIT_MAX = 10

OPTIONS = {
    "temperature": 0,
    "max_completion_tokens": 200,
}

_COMMON = """You are a senior SOC analyst. You will be shown ONE Snort intrusion-detection alert: the
alert header fields plus the full documentation of the rule that fired, together with
context retrieved from cybersecurity standards (NIST CSF 2.0, ISO/IEC 27001:2022, NIST SP
800-53 Rev 5). Use the standards context to compare the alert's behaviour against
recognised patterns, but judge THIS SINGLE ALERT.

Assign the alert a severity rank on a 1-5 scale, 1 the MOST severe:
  1 = CRITICAL. Direct exploitation attempt against a critical vulnerability (command
      execution, arbitrary code, privilege gain, admin compromise).
  2 = HIGH. Direct attack or exploitation attempt with real impact potential.
  3 = MEDIUM. Probing of a potentially vulnerable application; suspicious but not exploitation.
  4 = LOW. Light reconnaissance only.
  5 = INFORMATIONAL. Benign noise or activity with no realistic risk.

Rules for the task:
- Judge THIS SINGLE ALERT from its own record. Do not compare it to any other alert, and
  never count, aggregate, or summarize anything across alerts.
- Weigh every field present in the record. If a field is absent from the record (for example
  no cve_ids, no mitre data, no CVSS score), treat it as unknown and say so. Never invent or
  assume values that are not in the record.
- The standards context in [S1]..[S5] is supporting evidence only: mention it in your
  justification only when it matches what this alert actually does. If no context block is
  relevant, ignore it; never force a connection.
- The record includes Snort's own "priority" (a COARSER 1-3 scale, 1 = high), "classification"
  and "classtype". You may weigh them, but your 1-5 rank should refine, not copy, the coarse
  priority. Base your rank on the record as a whole.
- Use ONLY field names that actually appear in the record you were shown.
- Do not number or address the alert. Do not comment on the process.

Reply with EXACTLY ONE LINE and nothing else - no preamble, no markdown, no bullets, no
extra lines - in this strict format:

<rank 1-5> | <short 3-10 word justification citing the record's own evidence> | <comma-separated field names you weighed>

Format rules:
- Your reply is ONE line containing EXACTLY two "|" characters and three parts.
- rank is a single digit: 1, 2, 3, 4 or 5. 1 is the MOST severe, 5 the least. Never invert this.
- The justification is a SHORT phrase of 3 to 10 words, NOT a sentence, and contains no "|" characters.
- The third part is a comma-separated list of the record's field names you actually weighed,
  using the field names exactly as they appear in the record, for example:
  alert_message, cve_ids, rule_explanation, rule_vulnerability, mitre_tactic"""

SYSTEM = _COMMON

RETRY_REMINDER = """Your previous answer did not match the required format. Reply again with EXACTLY ONE line
containing EXACTLY two "|" characters and nothing else:
<rank 1-5> | <short 3-10 word justification> | <comma-separated field names>"""

RANK_RE = re.compile(r"^[1-5]$")

# Known record field names, for the informational metrics-vocabulary check.
KNOWN = {"alert_id", "alert", "rule_documentation", "rule_documentation_found"} | \
    {"timestamp", "alert_message", "rule_id", "protocol", "service", "source_ip",
     "destination_ip", "source_port", "destination_port", "direction", "packet_length",
     "gid", "sid", "rev", "priority", "classification"} | \
    {"msg", "rule_category", "flow", "rule_explanation", "content_matches", "metadata",
     "rule_text", "doc_url", "doc_found", "cve_ids", "references_text", "what_to_look_for",
     "mitre_id", "mitre_tactic", "mitre_technique", "rule_vulnerability",
     "false_positives", "known_usage", "classtype"}


def normalize(token: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", token.lower())


def build_query(entry: dict[str, Any]) -> str:
    """Compose the deterministic retrieval query, rule documentation weighted."""
    alert = entry["alert"]
    doc = entry.get("rule_documentation") or {}
    parts = [
        alert.get("alert_message", ""),
        doc.get("msg", ""),
        f"classtype: {doc['classtype']}" if doc.get("classtype") else "",
        doc.get("rule_category", ""),
        f"content: {doc['content_matches']}" if doc.get("content_matches") else "",
        doc.get("rule_explanation", ""),
    ]
    return " ".join(part for part in parts if part)


def build_user_message(entry: dict[str, Any], chunks: Sequence[RetrievedChunk]) -> str:
    """Return the standards context blocks, the full alert record, and the pipe instruction."""
    context = "\n\n".join(
        f"[S{position}]\n{retrieved.chunk.text}\n[/S{position}]"
        for position, retrieved in enumerate(chunks, start=1)
    )
    alert_json = json.dumps(entry, indent=2)
    return (
        "CONTEXT - cybersecurity standards retrieved for comparison\n"
        f"{context}\n\n"
        f"ALERT RECORD\n{alert_json}\n\n"
        "Severity-rank this single Snort alert. Reply with exactly one line: "
        "<rank 1-5> | <short 3-10 word justification> | <comma-separated field names>"
    )


def retrieve_evidence(
    store: ChunkStore,
    sparse_index: Any,
    query: str,
    limit: int,
) -> list[RetrievedChunk]:
    """Embed the query and run the standard hybrid retrieval path."""
    query_embedding = embed_query(query)
    return retrieve(
        query,
        query_embedding,
        store,
        sparse_index,
        limit=limit,
        mode=settings.retrieval_mode,
        rerank_enabled=settings.rerank_enabled,
        top_k_dense=settings.top_k_dense,
        top_k_bm25=settings.top_k_bm25,
        rrf_k=settings.rrf_k,
        rerank_candidates=settings.rerank_candidates,
        flashrank_model=settings.flashrank_model,
        flashrank_cache_dir=settings.flashrank_cache_dir,
    )


def serialize_chunks(chunks: Sequence[RetrievedChunk]) -> list[dict[str, Any]]:
    """Flatten retrieved chunks into the evidence schema stored per row."""
    serialized = []
    for position, retrieved in enumerate(chunks):
        chunk = retrieved.chunk
        serialized.append(
            {
                "rank": position + 1,
                "id": chunk.id,
                "text": chunk.text,
                "document": chunk.doc_name,
                "section": chunk.section,
                "control_id": chunk.control_id,
                "physical_page": chunk.page,
                "dense_cosine_score": retrieved.score,
                "rrf_score": retrieved.rrf_score,
                "rerank_score": retrieved.rerank_score,
            }
        )
    return serialized


def parse_line(content: str) -> dict[str, Any] | None:
    """Strict single-line contract: <1-5> | <justification> | <metrics>.

    The line must contain exactly two "|" separators. Anything else --
    multiple lines, extra pipes, missing parts -- is a format violation and
    returns None. We never coerce a malformed answer into a rank.
    """
    text = content.strip()
    if not text:
        return None
    lines = text.splitlines()
    if len(lines) != 1:
        return None
    parts = [part.strip() for part in lines[0].split("|")]
    if len(parts) != 3:
        return None
    rank_s, justification, metrics_s = parts
    if not RANK_RE.match(rank_s) or not justification:
        return None
    metrics = [token.strip() for token in metrics_s.split(",")]
    metrics = [token for token in metrics if token]
    # The record's field vocabulary is ~40 names; a verbose model may list most
    # of them (gemma2 did: 21 tokens). The cap only guards runaway lists, not
    # thorough ones - an earlier 12-token cap wrongly rejected good answers.
    if not metrics or len(metrics) > 60:
        return None
    return {"rank": int(rank_s), "justification": justification, "metrics_used": metrics}


def call_model(
    client: Any,
    model: str,
    user_message: str,
    limiter: groq_llm.RateLimiter,
) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
    """Call the model once, retry once, and record both attempts verbatim."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_message},
    ]
    attempts: list[dict[str, Any]] = []
    parsed: dict[str, Any] | None = None
    for _ in range(2):
        result = groq_llm.chat(
            client,
            model,
            messages,
            max_tokens=200,
            limiter=limiter,
        )
        content = result.content.strip()
        meta = {
            "done_reason": result.finish_reason,
            "prompt_eval_count": result.prompt_tokens,
            "eval_count": result.completion_tokens,
            "total_duration": result.total_time_s,
        }
        attempts.append({"content": content, "meta": meta})
        parsed = parse_line(content)
        if parsed is not None:
            break
        messages.append({"role": "user", "content": RETRY_REMINDER})
    status = "parsed" if parsed is not None else "failed"
    return attempts, status, parsed


def load_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_results_atomically(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def upsert_result(
    path: Path,
    rows: list[dict[str, Any]],
    row: dict[str, Any],
) -> None:
    key = (row["model"], row["alert_id"])
    updated = [existing for existing in rows if (existing["model"], existing["alert_id"]) != key]
    updated.append(row)
    write_results_atomically(path, updated)
    rows[:] = updated


def archive_if_exists(path: Path) -> None:
    """Move an existing deliverable to the next _vN slot; never delete records."""
    if not path.exists():
        return
    version = 1
    while path.with_name(f"{path.stem}_v{version}{path.suffix}").exists():
        version += 1
    path.rename(path.with_name(f"{path.stem}_v{version}{path.suffix}"))


def model_inventory(client: ollama.Client) -> dict[str, str]:
    response = client.list()
    return {
        model.model: model.digest
        for model in response.models
        if model.model is not None and model.digest is not None
    }


def validate_models(requested: Sequence[str], inventory: dict[str, str]) -> None:
    required = [canonical_model_name(settings.embed_model)]
    missing = [model for model in required if model not in inventory]
    if missing:
        sys.exit(
            "the embed model must be installed locally in Ollama while ranking/judge "
            f"LLMs run on Groq; missing exact tag: {', '.join(missing)}"
        )


def write_per_model_outputs(rows: Sequence[dict[str, Any]], n_alerts: int, started: str) -> None:
    """Write session and parsed deliverables per model, archiving old copies."""
    finished = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for model in sorted({row["model"] for row in rows}):
        tag = model.replace(":", "_").replace("/", "_")
        model_rows = [row for row in rows if row["model"] == model]
        session_path = CIL_ROOT / f"session_alert_rag_{tag}.json"
        parsed_path = CIL_ROOT / f"parsed_alert_rag_{tag}.json"
        archive_if_exists(session_path)
        archive_if_exists(parsed_path)

        session = {
            "model": model,
            "contract": CONTRACT,
            "system": SYSTEM,
            "retry_reminder": RETRY_REMINDER,
            "options": OPTIONS,
            "n_alerts": n_alerts,
            "started": started,
            "finished": finished,
            "calls": [
                {
                    "alert_id": row["alert_id"],
                    "query": row["query"],
                    "prompt": row["user_message"],
                    "retry_reminder": row["retry_reminder"],
                    "chunks": row["chunks"],
                    "attempts": row["attempts"],
                    "parsed": row["parsed"],
                    "status": row["status"],
                }
                for row in model_rows
            ],
        }
        session_path.write_text(json.dumps(session, indent=1) + "\n", encoding="utf-8")

        parsed_rows = [
            {
                "alert_id": row["alert_id"],
                **({"rank": row["parsed"]["rank"],
                    "justification": row["parsed"]["justification"],
                    "metrics_used": row["parsed"]["metrics_used"]} if row["parsed"] else {}),
                "raw": row["attempts"][-1]["content"],
                "attempts": len(row["attempts"]),
                "status": row["status"],
                "done_reasons": row["done_reasons"],
                "evidence": [
                    {
                        "rank": chunk["rank"],
                        "document": chunk["document"],
                        "section": chunk["section"],
                        "control_id": chunk["control_id"],
                        "dense_cosine_score": chunk["dense_cosine_score"],
                    }
                    for chunk in row["chunks"]
                ],
            }
            for row in model_rows
        ]
        parsed_path.write_text(json.dumps(parsed_rows, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {session_path.name} and {parsed_path.name} "
              f"({len(model_rows)} rows)")


def validate_run(rows: Sequence[dict[str, Any]], expected: int) -> None:
    """End-of-run summary; exit non-zero when any row failed to parse."""
    parsed = [row for row in rows if row["status"] == "parsed"]
    print(f"\nparsed {len(parsed)}/{expected}")
    for model in sorted({row["model"] for row in rows}):
        model_rows = [row for row in rows if row["model"] == model]
        ranks = [row["parsed"]["rank"] for row in model_rows if row["parsed"]]
        print(f"{model}: rank spread",
              dict(sorted(Counter(ranks).items())))
        if len(set(ranks)) == 1:
            print(f"  WARNING: model collapsed all alerts onto rank {ranks[0]} - "
                  "recorded failure, not smoothed")
    print("done_reason:",
          dict(sorted(Counter(reason for row in rows for reason in row["done_reasons"]).items())))
    retried = [row["alert_id"] for row in rows if len(row["attempts"]) == 2]
    print("retried once:", sorted(set(retried)) if retried else "none")
    if len(parsed) != expected:
        print("FAILED CALLS:")
        for row in rows:
            if row["status"] != "parsed":
                for attempt in row["attempts"]:
                    print(f"  alert {row['alert_id']} {row['model']} "
                          f"attempt: {attempt['content'][:160]!r}")
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", default=str(DEFAULT_SAMPLE))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--limit", type=int, default=None,
                        help="number of alerts to process (smoke: 2)")
    parser.add_argument(
        "--top-k",
        type=int,
        default=RETRIEVAL_LIMIT,
        help=(f"chunks reaching the model "
              f"(default {RETRIEVAL_LIMIT}, max {RETRIEVAL_LIMIT_MAX})"),
    )
    parser.add_argument("--resume", action="store_true",
                        help="skip (model, alert) rows already complete in --results")
    parser.add_argument("--rpm", type=int, default=groq_llm.DEFAULT_RPM)
    parser.add_argument("--rpd", type=int, default=groq_llm.DEFAULT_RPD)
    parser.add_argument("--tpm", type=int, default=groq_llm.DEFAULT_TPM)
    parser.add_argument("--tpd", type=int, default=groq_llm.DEFAULT_TPD)
    parser.add_argument("--budget-file", default=str(groq_llm.DEFAULT_TRACKER_PATH))
    args = parser.parse_args()

    if not 1 <= args.top_k <= RETRIEVAL_LIMIT_MAX:
        sys.exit(f"--top-k must be between 1 and {RETRIEVAL_LIMIT_MAX}")

    sample = json.loads(Path(args.input).read_text(encoding="utf-8"))
    entries = sample["entries"]
    assert len(entries) == 50
    if args.limit is not None:
        entries = entries[: args.limit]

    ollama_client = ollama.Client(host=settings.ollama_host)
    inventory = model_inventory(ollama_client)
    validate_models(args.models, inventory)
    client = groq_llm.client_from_env()
    tracker = groq_llm.DailyUsageTracker(Path(args.budget_file))
    limiter = groq_llm.RateLimiter(
        rpm=args.rpm,
        rpd=args.rpd,
        tpm=args.tpm,
        tpd=args.tpd,
        tracker=tracker,
    )

    store = ChunkStore()
    if store.count() == 0:
        sys.exit("vector store is empty - run Pipeline().index() first")
    sparse_index = Pipeline().sparse_index()

    results_path = Path(args.results)
    rows = load_results(results_path) if args.resume else []
    existing = {(row["model"], row["alert_id"]) for row in rows}

    started = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    expected = len(entries) * len(args.models)

    for i, entry in enumerate(entries, start=1):
        alert_id = entry["alert_id"]
        pending = [model for model in args.models if (model, alert_id) not in existing]
        if not pending:
            print(f"[{i:2d}/{len(entries)}] {alert_id} already complete", flush=True)
            continue

        query = build_query(entry)
        t0 = time.monotonic()
        chunks = retrieve_evidence(store, sparse_index, query, args.top_k)
        retrieval_ms = (time.monotonic() - t0) * 1000
        user_message = build_user_message(entry, chunks)

        try:
            for model in pending:
                t1 = time.monotonic()
                attempts, status, parsed = call_model(client, model, user_message, limiter)
                generation_ms = (time.monotonic() - t1) * 1000
                row = {
                    "schema_version": 1,
                    "run_id": started,
                    "model": model,
                    "model_digest": None,
                    "alert_id": alert_id,
                    "rule_id": entry["alert"].get("rule_id"),
                    "query": query,
                    "system": SYSTEM,
                    "user_message": user_message,
                    "retry_reminder": None if len(attempts) == 1 else RETRY_REMINDER,
                    "chunks": serialize_chunks(chunks),
                    "attempts": attempts,
                    "parsed": parsed,
                    "status": status,
                    "done_reasons": [attempt["meta"].get("done_reason") for attempt in attempts],
                    "latency_ms": {
                        "retrieval": round(retrieval_ms),
                        "generation": round(generation_ms),
                    },
                }
                upsert_result(results_path, rows, row)
                existing.add((model, alert_id))
                rank = row["parsed"]["rank"] if row["parsed"] else "-"
                justification = (
                    row["parsed"]["justification"][:80] if row["parsed"] else "(parse failed)"
                )
                print(
                    f"[{i:2d}/{len(entries)}] {alert_id} {model} -> "
                    f"rank={rank}  {justification}",
                    flush=True,
                )
        except groq_llm.GroqQuotaStop as error:
            print(error)
            return 2

    validate_run(rows, expected)
    write_per_model_outputs(rows, len(entries), started)

    cvss10 = [
        row for row in rows
        if "CVSS base score 10.0" in
        next(entry["rule_documentation"].get("rule_explanation", "")
             for entry in sample["entries"] if entry["alert_id"] == row["alert_id"])
        and row["parsed"]
    ]
    for row in cvss10:
        mark = "OK" if row["parsed"]["rank"] == 1 else "** expected 1"
        print(f"CVSS 10.0 spot-check: alert {row['alert_id']} {row['model']} "
              f"rank {row['parsed']['rank']} {mark}")

    bad_metrics = []
    for row in rows:
        if row["parsed"]:
            for token in row["parsed"]["metrics_used"]:
                if normalize(token) not in KNOWN:
                    bad_metrics.append((row["alert_id"], token))
    print("metrics tokens outside known field names:",
          bad_metrics if bad_metrics else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
