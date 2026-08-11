#!/usr/bin/env python3
"""Assemble the standards-grounded alert ranking report.

Reads the resumable run snapshot written by run_alert_rag.py
(alert_rag_run.jsonl), derives Snort ground truth from the alert records,
and writes two deliverables at CIL root:

    alert_rankings_rag.json         merged per-alert rows (rank, justification,
                                    metrics, retrieved evidence, mismatch flag,
                                    mismatch justification, judge verdict)
    alert_ranking_rag_report.md     the report

Two optional follow-up snapshots are merged when present: the mismatch
justifications from scripts/justify_alert_mismatches.py and the Groq judge
verdicts from scripts/judge_alert_rankings.py. When either file is absent
its fields and report sections are simply omitted.

Idempotent: existing deliverables are archived to the next _vN slot before
being overwritten, never deleted.

Usage:
    uv run python scripts/build_alert_rag_report.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

from csrs.alert_ranking import ANCHOR, is_mismatch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CIL_ROOT = PROJECT_ROOT.parent
DEFAULT_RESULTS = CIL_ROOT / "alert_rag_run.jsonl"
DEFAULT_SAMPLE = CIL_ROOT / "alert_sample_50.json"
DEFAULT_PRIOR = CIL_ROOT / "alert_rankings.json"
DEFAULT_JUSTIFY = CIL_ROOT / "alert_mismatch_justifications.jsonl"
DEFAULT_JUDGE = CIL_ROOT / "alert_judge_run.jsonl"
OUT = CIL_ROOT / "alert_ranking_rag_report.md"
OUTJSON = CIL_ROOT / "alert_rankings_rag.json"
MANIFEST = PROJECT_ROOT / "chroma_db" / "manifest.json"

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


def archive_if_exists(path: Path) -> None:
    """Move an existing deliverable to the next _vN slot; never delete records."""
    if not path.exists():
        return
    version = 1
    while path.with_name(f"{path.stem}_v{version}{path.suffix}").exists():
        version += 1
    path.rename(path.with_name(f"{path.stem}_v{version}{path.suffix}"))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    parser.add_argument("--prior", default=str(DEFAULT_PRIOR))
    parser.add_argument("--justifications", default=str(DEFAULT_JUSTIFY))
    parser.add_argument("--judge-results", default=str(DEFAULT_JUDGE))
    args = parser.parse_args()

    rows = []
    for line in Path(args.results).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        sys.exit(f"no rows in {args.results} - run scripts/run_alert_rag.py first")
    models = sorted({row["model"] for row in rows})
    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    entries = sample["entries"]
    by_id = {entry["alert_id"]: entry for entry in entries}

    run_ids = {row["run_id"] for row in rows}
    assert len(run_ids) == 1, f"mixed run ids in snapshot: {sorted(run_ids)}"
    run_id = sorted(run_ids)[0]

    prior = None
    if Path(args.prior).exists():
        prior = json.loads(Path(args.prior).read_text(encoding="utf-8"))
        assert len(prior) == 50

    rows_by = {(row["model"], row["alert_id"]): row for row in rows}
    assert len(rows_by) == len(rows), "duplicate (model, alert) rows in snapshot"
    parsed_rows = [row for row in rows if row["status"] == "parsed"]

    # Optional follow-up snapshots: mismatch justifications and Groq judge verdicts.
    # Absent files simply leave those fields/sections out of the deliverables.
    justifications = {}
    if Path(args.justifications).exists():
        j_rows = [json.loads(line) for line in
                  Path(args.justifications).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        justifications = {(row["model"], row["alert_id"]): row["justification"]
                          for row in j_rows if row["status"] == "parsed"}
        assert len(justifications) == len(
            [row for row in j_rows if row["status"] == "parsed"]
        ), "duplicate (model, alert) rows in justification snapshot"

    judge_rows = {}
    judge_model = None
    if Path(args.judge_results).exists():
        j_rows = [json.loads(line) for line in
                  Path(args.judge_results).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        judge_ids = {row["judge_model"] for row in j_rows}
        assert len(judge_ids) == 1, f"mixed judge models in snapshot: {sorted(judge_ids)}"
        judge_model = sorted(judge_ids)[0]
        judge_rows = {(row["model"], row["alert_id"]): row
                      for row in j_rows if row["status"] == "parsed"}
        assert len(judge_rows) == len(
            [row for row in j_rows if row["status"] == "parsed"]
        ), "duplicate (model, alert) rows in judge snapshot"

    manifest = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    corpus_lines = []
    for path, info in sorted(manifest.items()):
        corpus_lines.append(
            f"`{path}` — {info.get('chunk_count', '?')} chunks, "
            f"{info.get('page_count', '?')} pages"
        )

    ids = sorted(by_id)
    model_rank = {
        m: {aid: rows_by[(m, aid)]["parsed"]["rank"] for aid in ids
            if rows_by[(m, aid)]["status"] == "parsed"}
        for m in models
    }
    snort_prio = {aid: int(by_id[aid]["alert"]["priority"]) for aid in ids}
    classification = {aid: by_id[aid]["alert"].get("classification", "") for aid in ids}
    classtype = {aid: (by_id[aid].get("rule_documentation") or {}).get("classtype", "")
                 for aid in ids}

    agree = {m: sum(1 for aid in ids if model_rank[m].get(aid) == ANCHOR[snort_prio[aid]])
             for m in models}
    fail = {m: [aid for aid in ids if rows_by[(m, aid)]["status"] == "failed"] for m in models}
    retried = {m: [aid for aid in ids if len(rows_by[(m, aid)]["attempts"]) == 2]
               for m in models}
    done_reasons = {}
    for m in models:
        counter = Counter()
        for aid in ids:
            counter.update(rows_by[(m, aid)]["done_reasons"])
        done_reasons[m] = counter
    spread = {m: Counter(model_rank[m].values()) for m in models}

    cross = {m: Counter() for m in models}
    for m in models:
        for aid in ids:
            if aid in model_rank[m]:
                cross[m][(snort_prio[aid], model_rank[m][aid])] += 1

    bad_metrics = {m: [] for m in models}
    for m in models:
        for aid in ids:
            parsed = rows_by[(m, aid)]["parsed"]
            if parsed:
                bad_metrics[m] += [(aid, token) for token in parsed["metrics_used"]
                                   if normalize(token) not in KNOWN]

    cvss10 = [aid for aid in ids
              if "CVSS base score 10.0"
              in (by_id[aid].get("rule_documentation") or {}).get("rule_explanation", "")]
    big_diffs = {m: [aid for aid in ids if aid in model_rank[m]
                     and abs(model_rank[m][aid] - ANCHOR[snort_prio[aid]]) == 2]
                 for m in models}
    collapsed = {m: len(spread[m]) == 1 for m in models}
    pair_agree = {}
    for a, b in combinations(models, 2):
        pair_agree[(a, b)] = sum(1 for aid in ids
                                 if model_rank[a].get(aid) and model_rank[b].get(aid)
                                 and model_rank[a][aid] == model_rank[b][aid])

    # --- mismatch analysis (model rank vs anchored Snort ground truth) ---
    mismatch = {m: [aid for aid in ids if aid in model_rank[m]
                    and is_mismatch(model_rank[m][aid], snort_prio[aid])]
                for m in models}
    mismatch_by_prio = {m: Counter(snort_prio[aid] for aid in mismatch[m]) for m in models}

    # --- Groq judge results ---
    if judge_rows:
        judge_scores = {m: [judge_rows[(m, aid)]["verdict"]["score"] for aid in ids
                            if (m, aid) in judge_rows] for m in models}
        judge_mean = {m: (sum(v) / len(v) if v else None) for m, v in judge_scores.items()}
        judge_median = {}
        for m in models:
            values = sorted(judge_scores[m])
            n = len(values)
            judge_median[m] = (values[n // 2] if n % 2
                               else (values[n // 2 - 1] + values[n // 2]) / 2) if n else None
        judge_bands = {m: Counter(
            (0.0, 0.2) if v < 0.2 else (0.2, 0.4) if v < 0.4 else (0.4, 0.6) if v < 0.6
            else (0.6, 0.8) if v < 0.8 else (0.8, 1.0)
            for v in judge_scores[m]
        ) for m in models}
        judge_exact = {m: sum(1 for v in judge_scores[m] if v == 1.0) for m in models}
        judge_close = {m: sum(1 for v in judge_scores[m] if v >= 0.5) for m in models}
        judge_mismatch_mean = {}
        for m in models:
            rows_m = [judge_rows[(m, aid)]["verdict"]["score"] for aid in ids
                      if (m, aid) in judge_rows and aid in mismatch[m]]
            rows_ok = [judge_rows[(m, aid)]["verdict"]["score"] for aid in ids
                       if (m, aid) in judge_rows and aid not in mismatch[m]]
            judge_mismatch_mean[m] = (
                (sum(rows_m) / len(rows_m) if rows_m else None),
                (sum(rows_ok) / len(rows_ok) if rows_ok else None),
            )
        lowest = {}
        for m in models:
            scored = sorted(
                (judge_rows[(m, aid)]["verdict"]["score"],
                 judge_rows[(m, aid)]["verdict"]["reasoning"], aid)
                for aid in ids if (m, aid) in judge_rows
            )
            lowest[m] = scored[:3]

    # --- evidence statistics (section 6b) ---
    docs = {}
    for row in parsed_rows:
        docs[(row["model"], row["alert_id"])] = list(
            dict.fromkeys(chunk["document"] for chunk in row["chunks"])
        )
    doc_names = sorted({name for names in docs.values() for name in names})
    n_docs_per_alert = {
        m: Counter(len(docs.get((m, aid), [])) for aid in ids) for m in models
    }
    doc_by_priority = {name: Counter() for name in doc_names}
    for row in parsed_rows:
        for chunk in row["chunks"]:
            doc_by_priority[chunk["document"]][snort_prio[row["alert_id"]]] += 1
    top_control = Counter()
    iso_no_control = 0
    scores = []
    short_evidence = []
    for row in parsed_rows:
        for chunk in row["chunks"]:
            if chunk["control_id"]:
                top_control[f"{chunk['document']} / {chunk['control_id']}"] += 1
            if chunk["document"].startswith("ISO"):
                iso_no_control += 1
            scores.append(chunk["dense_cosine_score"] or 0.0)
        if len(row["chunks"]) < 5:
            short_evidence.append((row["alert_id"], row["model"], len(row["chunks"])))

    L = []
    w = L.append

    model_label = "model" if len(models) == 1 else "models"
    model_names = ", ".join(f"`{model}`" for model in models)

    w("# Standards-grounded alert severity ranking (RAG)")
    w("")
    w("50 distinct alerts sampled from `enriched_snort_alerts.json` were each sent **in full** "
      "— alert header plus complete rule documentation, **nothing removed** — and ranked by "
      f"the {model_label} recorded in this snapshot: {model_names}. Before the model "
      "saw each alert, a deterministic query composed from its record was run through the CSRS "
      "**hybrid retriever** (Chroma dense + BM25, RRF-fused) against a corpus of **three "
      "cybersecurity standards** (NIST CSF 2.0, ISO/IEC 27001:2022, NIST SP 800-53 Rev 5); the "
      "top 5 chunks were injected into the prompt as `[S1]..[S5]` context. Each model added "
      "three fields to the record: a **severity rank on a 1-5 scale (1 = most severe, "
      "5 = least severe)**, a **justification**, and the **metrics (record fields) it "
      "weighed**. The alerts' original Snort `priority`, `classification` and `classtype` "
      "were **included** in every record. The retrieved evidence chunks are recorded per "
      "alert, so every ranking is auditable against the standards. All responses are "
      "verbatim below.")
    w("")

    w("## 1. Run metadata")
    w("")
    w("| | |")
    w("|---|---|")
    w("| Provider | Groq API |")
    w("| Model | openai/gpt-oss-120b |")
    w(f"| Pipeline | CSRS at `{PROJECT_ROOT}` |")
    w(f"| Run id | `{run_id}` |")
    w(f"| Sample | `{args.sample}` (50 alerts) |")
    w(f"| Snapshot | `{args.results}` ({len(rows)} rows) |")
    w("| Options (all models) | `temperature=0`, `max_completion_tokens=200` |")
    w("| Retrieval | hybrid (dense top-20 + BM25 top-20, RRF k=60), rerank disabled, "
      "`limit=5` |")
    w("| Embedding model | `nomic-embed-text` (768-dim, task prefixes) |")
    w("| Corpus | " + "; ".join(corpus_lines) + " |")
    w("")
    w("| Model | Parameters | Context window | Calls parsed |")
    w("|---|---|---:|---:|")
    for m in models:
        w(f"| {m} | &mdash; | &mdash; | {len(model_rank[m])}/50 |")
    w("")

    w("## 2. Sampling")
    w("")
    w("Stratified by Snort priority so the sample spans all three of Snort's own priorities. "
      "The export's priority mix is 544 × 1, 500 × 2, 3 × 3; the sample takes **all 3 "
      "priority-3 alerts, 24 priority-1 and 23 priority-2**, drawn at random with "
      "`random.Random(42)` — reproducible. The 3 priority-3 alerts all belong to rule "
      "`1:987:32` (FILE-IDENTIFY `.htr` access), so that end of the scale is one rule only. "
      "The 50 alert_ids are identical to the previous runs', so the runs are directly "
      "comparable.")
    w("")
    w(f"{len(cvss10)} of the 50 sampled alerts carry `CVSS base score 10.0` in their rule "
      f"documentation (alert_ids {cvss10}) — the spot-checks in §6.")
    w("")

    w("## 3. Fields supplied to each model")
    w("")
    w("**Nothing was hidden.** Every record contains the full alert header — including "
      "`alert.priority` (Snort's own severity number), `alert.classification` (Snort's "
      "severity taxonomy) and `rule_documentation.classtype` — plus the complete rule "
      "documentation: CVSS text, CVE IDs, MITRE data, rule text and references.")
    w("")
    w("In addition, each prompt carries the **retrieved standards context** in `[S1]..[S5]` "
      "blocks: the top 5 chunks returned by the hybrid retriever for the query composed from "
      "the alert's `alert_message`, rule `msg`, `classtype`, `rule_category`, "
      "`content_matches` and `rule_explanation` (rule documentation weighted). The system "
      "prompt instructs the model to treat that context as supporting evidence only, "
      "mentioning it in the justification only when it matches what the alert actually does. "
      "The per-alert evidence (document, section, control_id, page, similarity score) is "
      "recorded in `alert_rankings_rag.json`.")
    w("")

    w("## 4. The prompt, verbatim")
    w("")
    w("**Pipe-line contract** — used by every model in the snapshot. System message:")
    w("")
    w("```text")
    w(rows_by[(models[0], ids[0])]["system"])
    w("```")
    w("")
    w("User message (one per alert; the record is embedded in full):")
    w("")
    w("```text")
    w("CONTEXT - cybersecurity standards retrieved for comparison")
    w("[S1]")
    w("{chunk text of the highest-ranked retrieved chunk, with its section breadcrumb}")
    w("[/S1]")
    w("[S2] ... [/S5]")
    w("")
    w("ALERT RECORD")
    w("{... the complete alert record as compact JSON, fields as in the source export ...}")
    w("")
    w("Severity-rank this single Snort alert. Reply with exactly one line: "
      "<rank 1-5> | <short 3-10 word justification> | <comma-separated field names>")
    w("```")
    w("")
    w("Retry reminder, appended once when the first answer failed the strict format check:")
    w("")
    w("```text")
    reminder = next(
        (row["retry_reminder"] for row in rows if row.get("retry_reminder")),
        "Your previous answer did not match the required format. Reply again with EXACTLY "
        "ONE line containing EXACTLY two \"|\" characters and nothing else:\n"
        "<rank 1-5> | <short 3-10 word justification> | <comma-separated field names>",
    )
    w(reminder)
    w("```")
    w("")

    w("## 5. Model responses, verbatim")
    w("")
    w("Each row is one alert. `Snort prio` is the priority inside the record each model saw. "
      "Justification and metrics are the exact strings each model returned; a row marked "
      "**(parse failed)** shows both raw attempts beneath the table.")
    w("")
    hdr = "| alert_id | rule_id | Snort prio | alert_message"
    sep = "|---|---|---:|---"
    for m in models:
        hdr += f" | {m} rank | {m} justification | {m} metrics"
        sep += "|---|---|---"
    w(hdr + " |")
    w(sep + " |")
    for aid in ids:
        entry = by_id[aid]
        cells = [str(aid), f"`{entry['alert']['rule_id']}`", str(snort_prio[aid]),
                 entry["alert"]["alert_message"]]
        for m in models:
            row = rows_by[(m, aid)]
            if row["status"] == "failed":
                cells += ["**(parse failed)**", "—", "—"]
            else:
                parsed = row["parsed"]
                cells += [f"**{parsed['rank']}**", parsed["justification"],
                          ", ".join(parsed["metrics_used"])]
        w("| " + " | ".join(cells) + " |")
    w("")
    for m in models:
        if fail[m]:
            w(f"### Parse failures — {m}")
            w("")
            for aid in fail[m]:
                row = rows_by[(m, aid)]
                w(f"**alert_id {aid}** (rule `{by_id[aid]['alert']['rule_id']}`), both "
                  f"attempts verbatim, `done_reason` per attempt:")
                w("")
                for i, attempt in enumerate(row["attempts"], start=1):
                    meta = attempt["meta"]
                    w(f"*attempt {i}: `done_reason={meta.get('done_reason')}`, "
                      f"prompt {meta.get('prompt_eval_count')} tokens, generated "
                      f"{meta.get('eval_count')} tokens*")
                    w("")
                    w("```text")
                    w(attempt["content"].rstrip())
                    w("```")
                    w("")
            w("")

    w("## 6. Model versus Snort (priority visible in every record)")
    w("")
    w("Each model ranks on **1-5 (1 = most severe)**. Snort's ground truth is coarser (1-3); "
      "for the exact-match stat it is mapped to its 5-point anchor — Snort 1 → model rank 1, "
      "Snort 2 → 3, Snort 3 → 5. The confusion tables show the raw ranks with no mapping. "
      "In this run, each model **saw** Snort's priority in every record, so an exact match "
      "can be "
      "simple copying; the prior non-RAG 1-5 run (`alert_rankings.json`) is the comparison "
      "baseline in §8.")
    w("")
    for m in models:
        n = len(model_rank[m])
        w(f"### {m}")
        w("")
        collapse_note = ""
        if collapsed[m]:
            cr = list(spread[m])[0]
            if cr in ANCHOR.values():
                sp = {v: k for k, v in ANCHOR.items()}[cr]
                collapse_note = (f" — all 50 were scored {cr}, so the {agree[m]} matches are "
                                 f"exactly the alerts whose Snort priority is {sp} (anchor "
                                 f"{cr}); the agreement is the collapse, not discrimination")
            else:
                collapse_note = (f" — all 50 were scored {cr}, which is not one of the anchor "
                                 f"ranks (1/3/5), so the collapse produces no exact matches")
        w(f"- Exact match with Snort priority: **{agree[m]}/50 ({100*agree[m]/50:.0f}%)**"
          f"{collapse_note}")
        w("- Rank distribution: "
          + ", ".join(f"{k}→{spread[m].get(k,0)}" for k in (1,2,3,4,5))
          + " vs sample composition 1→24, 2→23, 3→3")
        w("- `done_reason`: "
          + ", ".join(f"{k}={v}" for k, v in sorted(done_reasons[m].items()))
          + "; alerts retried once: "
          + (", ".join(map(str, retried[m])) if retried[m] else "none"))
        w("")
        w("Confusion table — rows are Snort's priority, columns the model's rank 1-5:")
        w("")
        w("| Snort \\ model | → 1 | → 2 | → 3 | → 4 | → 5 | Total |")
        w("|---:|---:|---:|---:|---:|---:|---:|")
        for sp in (1, 2, 3):
            cells = [cross[m].get((sp, k), 0) for k in (1, 2, 3, 4, 5)]
            w(f"| {sp} | " + " | ".join(map(str, cells)) + f" | {sum(cells)} |")
        w("")
        if collapsed[m]:
            w(f"**This model collapsed all {n} parsed alerts onto a single rank "
              f"({list(spread[m])[0]}) — recorded failure, not smoothed.**")
            w("")
        if big_diffs[m]:
            w("Two scale steps from the 5-point anchor (model rank vs anchor 1/3/5): "
              + ", ".join(f"alert {aid} ({model_rank[m][aid]} vs {ANCHOR[snort_prio[aid]]})"
                          for aid in big_diffs[m]))
            w("")
        if cvss10:
            lines = []
            for aid in cvss10:
                r = model_rank[m].get(aid, "unparsed")
                lines.append(f"alert {aid}: rank **{r}**" + (" (expected 1)" if r != 1 else ""))
            w(f"CVSS-10.0 spot-checks ({len(cvss10)} alerts with CVSS 10.0 in rule docs, "
              "expected rank 1): " + "; ".join(lines))
            w("")
        if bad_metrics[m]:
            w("Metrics tokens outside the known field vocabulary (model-authored names): "
              + ", ".join(f"`{t}` (alert {aid})" for aid, t in bad_metrics[m]))
            w("")
    for (a, b), num in pair_agree.items():
        w(f"`{a}` and `{b}` agree with each other on {num}/50 alerts.")
    w("")

    w("## 6b. Evidence statistics (what the standards retrieval actually returned)")
    w("")
    w("| Model | alerts with chunks from 1 doc | 2 docs | 3 docs |")
    w("|---|---:|---:|---:|")
    for m in models:
        c = n_docs_per_alert[m]
        w(f"| {m} | {c.get(1,0)} | {c.get(2,0)} | {c.get(3,0)} |")
    w("")
    w("Retrieved chunk counts by source document and the alert's Snort priority class "
      "(a chunk is counted once per alert it was retrieved for):")
    w("")
    w("| Document | p1 alerts | p2 alerts | p3 alerts | total |")
    w("|---|---:|---:|---:|---:|")
    for name in doc_names:
        c = doc_by_priority[name]
        w(f"| `{name}` | {c.get(1,0)} | {c.get(2,0)} | {c.get(3,0)} | {sum(c.values())} |")
    w("")
    if top_control:
        w("Most-retrieved control ids / sections (top 12):")
        w("")
        for label, count in top_control.most_common(12):
            w(f"- `{label}` — {count}")
        w("")
    if scores:
        mean = sum(scores) / len(scores)
        w(f"Dense-cosine similarity over all retrieved chunks: mean **{mean:.3f}**, "
          f"max **{max(scores):.3f}**. ")
    w(f"ISO/IEC 27001 chunks carry no parsed `control_id` (the Annex A heading pattern is not "
      f"recognized by the chunker), so `{iso_no_control}` of the retrieved chunks cite the "
      f"ISO document by section breadcrumb only.")
    if short_evidence:
        w("")
        w("Alerts whose retrieval returned fewer than 5 chunks: "
          + ", ".join(f"{aid} ({m}, {n})" for aid, m, n in short_evidence))
    w("")

    w("## 6c. Mismatch analysis (model rank vs anchored Snort ground truth)")
    w("")
    w("A rank is a **mismatch** when it is more than one step from the anchored ground "
      "truth: `|rank - ANCHOR[priority]| > 1` with `ANCHOR = {1:1, 2:3, 3:5}` — the same "
      "mapping the exact-match stat in §6 uses. For every mismatch, the model was "
      "re-queried with its own original `[S1]..[S5]` evidence, its recorded rank, and the "
      "Snort ground truth, and asked to explain why its rank differs and what led to its "
      "rank; those explanations are stored verbatim in `alert_rankings_rag.json` as "
      "`mismatch_justification`.")
    w("")
    w("| Model | mismatches | alerts | rate |")
    w("|---|---:|---:|---:|")
    for m in models:
        w(f"| {m} | {len(mismatch[m])} | {len(model_rank[m])} | "
          f"{100 * len(mismatch[m]) / len(model_rank[m]):.0f}% |")
    w("")
    w("By Snort priority (anchor in parentheses), mismatches / alerts:")
    w("")
    w("| Model | p1 (→1) | p2 (→3) | p3 (→5) |")
    w("|---|---:|---:|---:|")
    for m in models:
        cells = []
        for sp in (1, 2, 3):
            total = sum(1 for aid in ids if snort_prio[aid] == sp and aid in model_rank[m])
            cells.append(f"{mismatch_by_prio[m].get(sp, 0)}/{total}")
        w(f"| {m} | " + " | ".join(cells) + " |")
    w("")
    for m in models:
        if not mismatch[m]:
            w(f"**{m}: no mismatches.**")
            w("")
            continue
        w(f"### Mismatch rows — {m}")
        w("")
        for aid in sorted(mismatch[m]):
            justification = justifications.get((m, aid))
            if justification:
                w(f"- **alert {aid}** (Snort p{snort_prio[aid]} → anchored "
                  f"{ANCHOR[snort_prio[aid]]}): model rank **{model_rank[m][aid]}**")
                w("")
                w(f"  > \"{justification}\"")
                w("")
            else:
                missing_note = ("— no justification pass ran" if not justifications
                                else "— justification missing")
                w(f"- **alert {aid}** (Snort p{snort_prio[aid]} → anchored "
                  f"{ANCHOR[snort_prio[aid]]}): model rank **{model_rank[m][aid]}** "
                  f"{missing_note}")
                w("")
    w("")

    w("## 6d. LLM-as-judge: Groq GPT-OSS scores the local rankings")
    w("")
    if not judge_rows:
        w(f"The judge snapshot (`{args.judge_results}`) is missing — section skipped. "
          "Run `scripts/judge_alert_rankings.py` to score every parsed ranking.")
    else:
        w(f"Every parsed (model, alert) ranking was scored on **0-1** by "
          f"`{judge_model}` (Groq API, `temperature=0`, strict JSON schema). The judge "
          f"received the local model's rank/justification/metrics, the **complete "
          f"original alert** (header + full rule documentation) and the ground truth "
          f"(Snort priority + anchored rank). Rubric: **1.0** exact match, **0.5–0.9** "
          f"within one step of the anchored rank, **0.0–0.4** more than one step away; "
          f"justification quality nudges the score within each band. Judge verdicts "
          f"(score + reasoning) are stored in `alert_rankings_rag.json`.")
        w("")
        w("| Model | mean | median | exact (1.0) | ≥ 0.5 |")
        w("|---|---:|---:|---:|---:|")
        for m in models:
            mean = f"{judge_mean[m]:.3f}" if judge_mean[m] is not None else "—"
            median = f"{judge_median[m]:.3f}" if judge_median[m] is not None else "—"
            w(f"| {m} | {mean} | {median} | {judge_exact[m]} | "
              f"{judge_close[m]} |")
        w("")
        w("Score distribution (0.0–1.0):")
        w("")
        w("| Model | 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |")
        w("|---|---:|---:|---:|---:|---:|")
        for m in models:
            w("| " + " | ".join(
                [m] + [str(judge_bands[m].get((lo, hi), 0))
                       for lo, hi in ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))]
            ) + " |")
        w("")
        w("Agreement with the mismatch flag — mean judge score on mismatch rows vs "
          "non-mismatch rows (empty cell when a class has no rows):")
        w("")
        w("| Model | mismatch rows | non-mismatch rows |")
        w("|---|---:|---:|")
        for m in models:
            mm, ok = judge_mismatch_mean[m]
            w(f"| {m} | {f'{mm:.3f}' if mm is not None else '—'} | "
              f"{f'{ok:.3f}' if ok is not None else '—'} |")
        w("")
        for m in models:
            w(f"### Lowest-scored rankings — {m}")
            w("")
            if not lowest[m]:
                w("_none_")
                w("")
                continue
            for score, reasoning, aid in lowest[m]:
                w(f"- **alert {aid}**: judge score **{score:.2f}** — "
                  f"model rank **{model_rank[m].get(aid, '?')}** vs anchored "
                  f"{ANCHOR[snort_prio[aid]]}. Judge reasoning: \"{reasoning}\"")
            w("")
    w("")

    w("## 7. Caveats")
    w("")
    w("- **N=3 for priority 3.** The dataset holds only 3 priority-3 alerts, all from one "
      "rule (`1:987:32`), so that column of the confusion table is thin and not "
      "representative of the priority-3 population.")
    w("- **Single hosted model.** The production experiment uses the hosted 120B-class "
      "`openai/gpt-oss-120b` model through the Groq API, so its results do not establish "
      "how other models or providers would rank the same alerts.")
    w("- **Agreement can be pure copying.** The answer was visible in the input, so a model "
      "that echoes `priority` scores an exact match without weighing anything. Deviations "
      "from the visible priority are more informative than matches in this run.")
    w("- **The exact-match stat uses mapped anchors.** Snort's 1-3 priority is compared "
      "against the 5-point anchors 1, 3 and 5 (Snort 1 → 1, 2 → 3, 3 → 5). This is a "
      "modeling choice; the confusion tables and `alert_rankings_rag.json` carry the raw, "
      "unmapped ranks.")
    w("- **`metrics_used` are model-authored field names.** They may not exactly match the "
      "record's keys; mismatches are listed in §6 rather than silently normalized.")
    w("- **Same rule documentation repeats.** Alerts of the same rule carry identical "
      "`rule_documentation`; the calls re-send it. Judgement is per-alert by design.")
    w("- **Retrieval quality is query-vocabulary dependent.** The composed query is built "
      "from the alert's own wording, so standards language that shares no terms with the "
      "alert (for example ISO Annex A controls vs Snort's `content_matches` tokens) may not "
      "be retrieved even when relevant. §6b reports what was actually retrieved.")
    w("- **The standards context is evidence, not a rank.** The system prompt instructs the "
      "model to use `[S1]..[S5]` only as supporting comparison material and never force a "
      "connection; the justification column shows whether the model cited the context or "
      "ignored it.")
    w("- **ISO control ids are absent.** ISO chunks carry `control_id=None` because the "
      "chunker's control-id patterns match CSF and SP 800-53 headings, not Annex A (`A.5.1`) "
      "headings; ISO citations use section breadcrumbs instead.")
    w("- **Retry policy.** A malformed first answer triggered exactly one retry with the "
      "reminder above; both attempts are recorded. Anything still failing is shown verbatim "
      "in §5, never coerced into a rank.")
    w("")

    w("## 8. Compared with the prior non-RAG 1-5 run (same 50 alerts, priority visible)")
    w("")
    if prior is None:
        w(f"The prior run data (`{args.prior}`) is missing — comparison skipped.")
    else:
        prior_rank = {
            m: {row["alert_id"]: row[m]["rank"] for row in prior
                if row.get(m, {}).get("status") == "parsed"}
            for m in models
        }
        prior_spread = {m: Counter(prior_rank[m].values()) for m in models}
        w("The previous run (`alert_rankings.json`) used the same 50 alerts, the same "
          "visible fields and an identical prompt **without** the standards context. The "
          "table shows each model's rank spread before and after adding RAG context, and how "
          "often the RAG run changed the model's rank per alert:")
        w("")
        w("| Model | non-RAG spread | RAG spread | ranks used (non-RAG → RAG) | "
          "rank changed |")
        w("|---|---:|---:|:--:|---:|")
        for m in models:
            changed = sum(1 for aid in ids
                          if aid in model_rank[m] and aid in prior_rank[m]
                          and model_rank[m][aid] != prior_rank[m][aid])
            used_prior = len([k for k in (1,2,3,4,5) if prior_spread[m].get(k)])
            used_rag = len([k for k in (1,2,3,4,5) if spread[m].get(k)])
            w(f"| {m} | "
              + ", ".join(f"{k}→{prior_spread[m].get(k,0)}" for k in (1,2,3,4,5))
              + " | "
              + ", ".join(f"{k}→{spread[m].get(k,0)}" for k in (1,2,3,4,5))
              + f" | {used_prior} of 5 → {used_rag} of 5 | {changed}/50 |")
        w("")
        per_model_lines = []
        for m in models:
            moved = [(aid, prior_rank[m].get(aid), model_rank[m].get(aid))
                     for aid in ids
                     if aid in model_rank[m] and aid in prior_rank[m]
                     and model_rank[m][aid] != prior_rank[m][aid]]
            moved.sort()
            if moved:
                per_model_lines.append(
                    f"{m}: {len(moved)} alerts moved — "
                    + "; ".join(f"{aid} {a}→{b}" for aid, a, b in moved)
                )
        for line in per_model_lines:
            w(line)
            w("")
        if cvss10:
            lines = []
            for aid in cvss10:
                cells = []
                for m in models:
                    before = prior_rank[m].get(aid, "-")
                    after = model_rank[m].get(aid, "-")
                    cells.append(f"{m}: {before} → {after}")
                lines.append(f"alert {aid} ({' / '.join(cells)})")
            w("CVSS-10.0 alerts (expected rank 1), non-RAG → RAG: " + "; ".join(lines))
            w("")
    w("")

    # ---- merged deliverable ----
    merged = []
    for aid in ids:
        entry = by_id[aid]
        first_model_row = rows_by[(models[0], aid)]
        row = {
            "alert_id": aid,
            "rule_id": entry["alert"]["rule_id"],
            "alert_message": entry["alert"]["alert_message"],
            "snort_priority": snort_prio[aid],
            "classification": classification[aid],
            "classtype": classtype[aid],
            "query": first_model_row["query"],
            "retrieved_chunks": first_model_row["chunks"],
        }
        for m in models:
            r = rows_by[(m, aid)]
            if r["status"] == "failed":
                row[m] = {"status": "failed", "raw": [a["content"] for a in r["attempts"]]}
            else:
                p = r["parsed"]
                model_row = {"status": "parsed", "rank": p["rank"],
                             "justification": p["justification"],
                             "metrics_used": p["metrics_used"],
                             "raw": r["attempts"][-1]["content"],
                             "done_reason": r["done_reasons"][-1]}
                model_row["mismatch"] = is_mismatch(p["rank"], snort_prio[aid])
                if (m, aid) in justifications:
                    model_row["mismatch_justification"] = justifications[(m, aid)]
                if (m, aid) in judge_rows:
                    j = judge_rows[(m, aid)]
                    verdict = j["verdict"]
                    model_row["judge"] = {
                        "score": verdict["score"],
                        "reasoning": verdict["reasoning"],
                        "model": j["judge_model"],
                        "latency_ms": j["latency_ms"],
                    }
                row[m] = model_row
        merged.append(row)

    archive_if_exists(OUTJSON)
    archive_if_exists(OUT)
    OUTJSON.write_text(json.dumps(merged, indent=1) + "\n", encoding="utf-8")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"wrote {OUT}")
    print(f"wrote {OUTJSON}")
    for m in models:
        judge_note = ""
        if judge_rows:
            mean = judge_mean[m]
            judge_note = (f", judge mean {mean:.3f} ({len(judge_scores[m])} rows)"
                          if mean is not None else ", judge mean n/a")
        print(f"{m}: parsed {len(model_rank[m])}/50, exact match {agree[m]}/50 "
              f"({100*agree[m]/50:.0f}%), mismatches {len(mismatch[m])}/50, "
              f"spread {dict(sorted(spread[m].items()))}, failures {len(fail[m])}"
              f"{judge_note}")
    for (a, b), num in pair_agree.items():
        print(f"{a} vs {b}: agree {num}/50")
    return 0


if __name__ == "__main__":
    sys.exit(main())
