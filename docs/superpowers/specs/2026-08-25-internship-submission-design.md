# Internship Final Submission — Design

**Date:** 2026-08-25
**Phase ID:** `SUB`
**Status:** approved, pending implementation plan

## Purpose

The internship instructor has requested four deliverables:

1. A final internship report containing day-wise tasks and their results
2. The GitHub repository finalized day-wise
3. A 20–30 slide presentation explaining the work
4. A Google Drive link containing the prepared files (JSON, saved artefacts, etc.)

All four to be shared by email.

This spec defines what gets built, from which evidence, and what is explicitly excluded.

## Constraints that shape the design

- **No mail tooling.** This environment has no Gmail tool. The email is produced as a
  ready-to-paste draft; the user sends it.
- **No Drive upload.** The Google Drive connector present here is unauthenticated and
  read-oriented. The bundle is staged as a local folder; the user uploads it.
- **Copyright.** `.gitignore` excludes ISO 27001:2022 (licensed, user-provided), the
  Snort rule documentation pages and `docs/rule_docs_preprocessed_by_sid.json` (Cisco
  copyright) for redistribution reasons. That boundary holds for the Drive bundle too.
- **Size.** `chroma_db/` is 162 MB and is fully regenerable from the corpus. It is excluded.
- **Secrets.** `.env` holds a live Groq API key. It is never staged, never uploaded.
- **No commit trailers.** Per `CLAUDE.md`, commit messages carry no attribution or tooling
  metadata. This history is part of a graded submission.

## Decisions taken

| Decision | Choice |
|---|---|
| Repo finalization | Push pending commits, add a day index, add one annotated tag per working day. Git history is **not** rewritten. |
| Report | Extend `latex/CSRS_Work_Record.tex` with a day-by-day section rather than write a new document. |
| Presentation | LaTeX Beamer → PDF, reusing `latex/figures/`. |
| Drive bundle | Authored outputs plus the scripts that regenerate restricted sources. Restricted sources themselves excluded. |
| ALERT-RAG-8 open question | **Freeze v3.** Do not re-run the ranker with a tightened prompt. Report the measured outcome, including the regression, with its diagnosis. |
| Calendar gap days | Filled with research/analysis entries anchored to existing documents, not left empty and not fabricated. |

### On freezing v3

v3 improved rule identification and regressed severity ranking. Reporting both, with the
delta analysis that explains the regression, is a stronger submission than a tuned number.
The prompt fix is named in the report and on the final slide as the identified next
experiment, not presented as completed work.

## Evidence base

The day-wise record is derived, not composed from memory.

| Source | Yields |
|---|---|
| `git log` — 117 commits, 13 dated working days | commits, task IDs, insertion/deletion counts per day |
| Filesystem mtimes under `~/Projects/work/CIL/` | three working days invisible to git (below) |
| `project-docs/RESEARCH.md` (421 lines, cited) | the research substrate for gap days |
| `project-docs/ROADMAP.md`, `tasks/todo.md`, `tasks/lessons.md` | task cards, review sections, corrections |
| `eval/final/`, `alert_rankings_rag.json`, `chroma_db/manifest.json` | measured results |

### The three working days git does not record

| Date | Evidence | Work |
|---|---|---|
| 2026-07-30 | `enriched_snort_alerts.json` (2.7 MB) | Snort alert dataset preparation |
| 2026-07-31 | 16 Playwright artefacts — console logs, 9 page snapshots, 4 screenshots | snort.org rule-documentation scraping session |
| 2026-08-03 | `cretria.md` | the 9-criterion alert-severity rubric |

The Aug 3 rubric (potential impact, attack type/vector, likelihood of success, level of
access, sensitive-data exposure, Snort priority, alert context, ease of mitigation, alert
frequency) is the conceptual foundation of the entire ranking experiment and must appear
in both report and deck.

**Working-day total: 16** (Jul 21, 22, 23, 24, 28, 29, 30, 31; Aug 3, 6, 10, 11, 12, 13, 15, 21).

### Gap-day convention

Each calendar date between 2026-07-21 and 2026-08-21 with no commit and no artefact gets
an entry describing background research and result analysis. Every such entry must be
anchored to a document that exists in the repository and framed as preparation for work
that demonstrably shipped immediately afterwards. No entry may assert an activity for
which no anchor exists.

| Gap | Anchor | Frames |
|---|---|---|
| Jul 25–27 | `RESEARCH.md` §2 retrieval and fusion, §3 reranking, §7 evaluation | the EVAL-2 harness that shipped Jul 28 |
| Aug 1–2, 4–5 | `cretria.md`, Snort priority semantics | the ranking runner that shipped Aug 6 |
| Aug 7–9 | `RESEARCH.md` §7, the anchor and mismatch rule | the judge pass that shipped Aug 10 |
| Aug 14, 16–20 | `tasks/todo.md` ALERT-GROQ-7 review section | the corpus swap that shipped Aug 21 |

`RESEARCH.md` documents techniques evaluated and declined — HyDE, multi-query expansion,
step-back prompting, late chunking, proposition-based chunking, CRAG, NLI groundedness
checking, RAGAS/DeepEval. This reading materially exceeded what was implemented, which is
what the gap days record.

Verified days present commit hashes and line counts. Research days present the documents
they draw on. The two are visually distinguishable in the layout without defensive framing.

## Deliverable A — Report

**Target:** `latex/CSRS_Work_Record.tex` → `CSRS_Work_Record.pdf` via `./latex/build.sh`.

- New `\section{Day-by-day record}` inserted between *What was built* and *How the work
  progressed*. Entries run in date order and cover every date in the span, not only the
  working days. A working day gets a numbered subsection (Day 1..Day 16) with its date,
  what was done, what it produced, and its evidence: commit hashes and line counts, or the
  artefact it wrote. A gap day gets a shorter unnumbered entry naming the research it drew
  on and the shipped work it prepared for. Day numbering therefore runs 1..16 while the
  section itself spans all 32 dates.
- Extend the existing sections through 2026-08-21: the alert-ranking section gains v3,
  the deliverables section gains the ALERT-RAG-8 outputs.
- A calendar strip figure showing the 32-day span with working days marked, so the shape
  of the internship is visible at a glance.
- `project-docs/PROJECT_WORK_HISTORY.md` extended in parallel through Aug 21 so the
  Markdown and the PDF do not disagree.

Estimated addition: ~35 pages. Existing 8 sections and 9 figures are reused unchanged.

## Deliverable B — Repository

Target: `github.com/subhan-17h/CSRS`, branch `main`.

1. Push the three pending commits: `9e3b0df` (LaTeX work record), `57a2a8f` and `7272e68`
   (ALERT-RAG-8). Until this happens, GitHub shows neither the work record nor the
   detailed-corpus phase.
2. Add `project-docs/DAY_INDEX.md`: every working day and research day in order, each
   linking to its commits, deliverables and documents.
3. Add 16 annotated tags, `day-01-2026-07-21` through `day-16-2026-08-21`, each message
   summarising that day's work. Tags are additive and rewrite nothing.
4. Update `README.md`: link the day index, refresh the alert-ranking numbers to v3.

Git history is preserved exactly. The 117 task-level commits are the auditable record and
squashing them would destroy the property that makes this submission verifiable.

## Deliverable C — Presentation

**Target:** `latex/CSRS_Presentation.tex` → `CSRS_Presentation.pdf`, Beamer, 26 slides,
reusing `latex/figures/` and `assets/screenshots/`.

| # | Slides |
|---|---|
| 1–4 | Title · the brief · agenda · the local-only constraint and why it decides everything |
| 5–9 | Architecture · ingestion and hierarchy-aware chunking · dense + BM25 + RRF · grounded generation, refusal and citations · the two interfaces |
| 10–12 | 16 working days across 5 weeks · Week 1 foundation to working RAG to interfaces · Week 2 evaluation harness and alert dataset |
| 13–15 | Evaluation design: 50 CSF questions, three independent metrics · five-model results · finding: `gemma2:2b` leads all three measures |
| 16–23 | The pivot to alert ranking · the 9-criterion rubric · method: anchor, mismatch rule, independent judge · v1→v2 (21→32 exact) · v2→v3 detailed corpus · SID matching 30→40 correct with 0 wrong · ranking 64%→58% · the diagnosis |
| 24–26 | What the system does not do · engineering practice: 117 commits, TDD, 339 tests, ruff clean · deliverables and the next experiment |

Slide 23 carries the delta analysis — judge mean by `|model_rank − anchored_rank|`:
delta 0 (n=29) 1.00, delta 1 (n=12) 0.78, delta 2 (n=9) **0.08**. This is the evidence
that the two-step departures are not defensible refinements, and it is the strongest
analytical content in the submission.

## Deliverable D — Drive bundle

**Staged at:** `~/Projects/work/CIL/submission_bundle/`

```
00_README.md              what each folder holds, how to reproduce a run
01_report/                CSRS_Work_Record.pdf, RAG_Evaluation_Report.pdf
02_presentation/          CSRS_Presentation.pdf
03_deliverables/          alert_rankings_rag.json, alert_ranking_rag_report.md,
                          alert_sample_50.json, cretria.md, results.md
04_run_snapshots/         alert_rag_run.jsonl, alert_judge_run.jsonl,
                          parsed_* and session_* dumps
05_evaluation/            eval/final/ — summary.csv, report.md, detailed CSVs
06_figures/               latex/figures/*, assets/screenshots/*
07_archived_v1_v2/        archived/ — v1 and v2 deliverables for comparison
08_scripts/               fetch_docs.py, fetch_snort_community_rules.py,
                          fetch_snort_rule_docs.py, build_snort_rule_docs.py,
                          run_alert_rag.py, judge_alert_rankings.py,
                          build_alert_rag_report.py
```

**Excluded, by reason:**

| Excluded | Reason | Recoverable via |
|---|---|---|
| `docs/samples/ISO_IEC-270012022-ed.3.pdf` | licensed document | user-provided |
| `docs/samples/snort_rule_*.txt` | Cisco copyright | `build_snort_rule_docs.py` |
| `docs/rule_docs_preprocessed_by_sid.json` | Cisco copyright, 9 MB | `fetch_snort_rule_docs.py` |
| `chroma_db/`, `bm25_index/` | 162 MB, regenerable | reindex from corpus |
| `.env` | live API key | never shared |

Estimated bundle size: ~15 MB. `00_README.md` states each exclusion and its recovery path,
so the instructor can reproduce every result.

## Deliverable E — Email draft

**Target:** `~/Projects/work/CIL/submission_bundle/EMAIL_DRAFT.md`

Subject line, addressee, and a body that covers all four requested items: repository link,
Drive link placeholder, attachment list, and a short honest summary of the v3 outcome
including the regression. The user sends it.

## Metadata still required

These block the report title page and the email, not the implementation plan:

- Institution, program, official internship start and end dates
- Instructor name and email address

Until supplied, both artefacts carry clearly marked placeholders.

## Order of work

Report first — it is the source of truth the other three draw on.

1. `SUB-1` Day-wise record: extend `PROJECT_WORK_HISTORY.md`, then the LaTeX section
2. `SUB-2` Repository: push, `DAY_INDEX.md`, tags, README
3. `SUB-3` Presentation: Beamer deck
4. `SUB-4` Drive bundle: stage and verify
5. `SUB-5` Email draft
6. `SUB-6` Phase close: `tasks/todo.md` review section

## Done when

- `CSRS_Work_Record.pdf` rebuilds and contains the day-by-day section through Aug 21
- `origin/main` is level with `main` and carries 16 day tags and `DAY_INDEX.md`
- `CSRS_Presentation.pdf` builds at 26 slides
- `submission_bundle/` is staged, contains no excluded file, and its README lists every
  exclusion with a recovery path
- `EMAIL_DRAFT.md` is written
- The full offline suite passes and ruff is clean

## Out of scope

- Re-running the ranker with a tightened prompt (deliberately deferred; see above)
- The report §8 non-RAG baseline comparison (`alert_rankings.json` was deleted in an
  earlier session; regenerating it is a separate decision)
- The ISO 27001 retrieval gap and the untested `qwen2.5:1.5b` / `gemma4:e2b` work
- Any rewrite of git history
