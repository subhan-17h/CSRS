# CSRS — Internship Submission Bundle

Muhammad Subhan Amir · 21 July – 21 August 2026 · https://github.com/subhan-17h/CSRS

Everything here was produced by the project itself. No figure is transcribed and no result
is retyped: the charts are generated from the committed evaluation artefacts, and both alert
deliverables regenerate byte-identically from the run snapshots in `04_run_snapshots/`.

Rebuild this folder at any time with `scripts/stage_submission_bundle.sh`.

## What is in each folder

| Folder | Contents |
|---|---|
| `01_report/` | The final report (`CSRS_Work_Record.pdf`), the evaluation report, the day-by-day narrative in Markdown, and the day index. |
| `02_presentation/` | The 33-slide presentation (`CSRS_Presentation.pptx`) and its PDF backup (`CSRS_Presentation.pdf`). |
| `03_deliverables/` | The alert-ranking JSON and Markdown deliverables, the 50-alert sample, the nine-criterion severity rubric, and the evaluation results summary. |
| `04_run_snapshots/` | Every request, retrieved passage, model response and judge verdict, as JSONL. These are what make the results reproducible without calling a model. |
| `05_evaluation/` | The 250-row five-model benchmark: summary CSV, detailed CSVs, and the report. |
| `06_figures/` | Every chart in the report and slides (`charts/`), the UI and terminal screenshots (`screenshots/`), and the architecture diagram as SVG. |
| `07_archived_v1_v2/` | The superseded v1 and v2 deliverables and run snapshots, and the short-form corpus, kept so the three runs can be compared directly. |
| `08_scripts/` | The scripts that fetch the corpus, build the rule documents, run the ranker and judge, and build the reports. |

## What is deliberately not here, and how to get it

| Excluded | Why | How to recreate it |
|---|---|---|
| `ISO_IEC-270012022-ed.3.pdf` | Licensed document; not mine to redistribute. | Supply your own copy in `docs/samples/`. |
| `snort_rule_*.txt` (4,017 files) | Rendered from Cisco-copyrighted rule documentation. | `08_scripts/build_snort_rule_docs.py` |
| `rule_docs_preprocessed_by_sid.json` (9 MB) | Same copyright; the source the documents are rendered from. | `08_scripts/fetch_snort_rule_docs.py` |
| `NIST.SP.800-53r5.pdf` | Public domain, but large and fetched rather than shipped. | `08_scripts/fetch_docs.py` |
| `chroma_db/`, `bm25_index/` | 162 MB, and fully regenerable. | Re-index the corpus. |
| `.env` | Contains a live API key. | Copy `.env.example` and supply your own. |

The same exclusions are enforced by the repository's `.gitignore`, for the same reasons.

## Reproducing the results

From a clone of the repository:

```bash
uv run --group eval python -m pytest -q -m "not ollama and not docling"   # 339 tests
uv run ruff check .
uv run python scripts/build_snort_rule_docs.py                            # rebuild the corpus
uv run python scripts/build_alert_rag_report.py                           # rebuild both deliverables
```

The last command regenerates `alert_rankings_rag.json` and `alert_ranking_rag_report.md`
from the run snapshots, making zero API calls.

## The headline results

**Answer quality** — 50 questions on NIST CSF 2.0, five local models, three independent
metrics that are never combined into one score. `gemma2:2b` led all three (82% cosine pass,
100% BERTScore pass, 90% judge pass).

**Alert severity ranking** — 50 real Snort alerts, ranked from retrieved evidence, with the
rule identity withheld from the ranker and an independent model judging.

| Run | Exact rank matches | Mismatches | Correct rule matches | Judge mean |
|---|---:|---:|---:|---:|
| v1 (12 Aug) | 21/50 | 23/50 | not measured | 0.586 |
| v2 (13 Aug) | **32/50** | **4/50** | 30/50 (4 wrong) | **0.868** |
| v3 (21 Aug) | 29/50 | 9/50 | **40/50 (0 wrong)** | 0.780 |

v3 replaced the one-line rule documents with the full published documentation. Rule
identification reached the ceiling retrieval allows — 40 correct, none wrong, 10 honest
abstentions — while severity ranking regressed. Section 6 of the report grades every ranking
by its distance from ground truth and shows why: one-step revisions still score 0.78, but
two-step departures score 0.08. The added CVE and explanation text leads the ranker to weigh
narrative severity above the Snort priority.

That regression is reported rather than tuned away. The prompt change that would test the
cause is named in the report and has deliberately not been run.
