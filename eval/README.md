# CSF-Only RAG Evaluation

This directory contains the end-to-end evaluation layer for the local RAG assistant. The
version-two benchmark uses 50 draft questions grounded only in the 32-page
`docs/samples/NIST.CSWP.29_CSF-2.0.pdf`. It compares the same questions, retrieval
settings, five-chunk generator context, prompt, and generation settings across:

- `llama3.2:latest`
- `qwen2.5:1.5b`
- `gemma2:2b`
- `phi4-mini:latest`
- `gemma4:e2b`

The benchmark reports three independent metrics. It does not calculate a combined score
or overall pass.

## Evaluation metrics

### Cosine similarity

The evaluator embeds each generated answer and accepted reference answer with the local
`nomic-embed-text:latest` model using the symmetric `clustering:` prefix. It retains the
highest reference score and applies the fixed pass threshold `>= 0.75`.

Cosine similarity measures broad semantic agreement. It can miss incorrect numbers,
negation, modality, exceptions, and incomplete lists, so its pass decision is not proof
of factual correctness.

### BERTScore

BERTScore compares candidate and reference tokens with the pinned
`FacebookAI/roberta-large` snapshot
`722cf37b1afa9454edce342e7895e588b6ff1d59`, layer 17, on CPU. The evaluator uses raw
scores with no IDF and no baseline rescaling. It reports precision, recall, and F1,
retains the full score tuple from the accepted reference with the highest F1, and applies
the pass threshold `F1 >= 0.85`.

The pinned model must be present in the local Hugging Face cache before evaluation. It
can be prepared with the repository's model-warming command.

### Groq LLM judge

The optional judge uses `openai/gpt-oss-120b` at temperature `0`. It receives the
question, generated and reference answers, atomic required claims, gold evidence, and
the five retrieved chunks supplied to the generator. Candidate-model identity is hidden.

The judge scores correctness, completeness, faithfulness, and relevance from 0 to 4. It
also records missing claims, unsupported additions, contradictions, and a
`pass | partial | fail` verdict. Responses use strict JSON and transient API failures
receive bounded retries. The judge is a consistent review aid, not a substitute for a
cybersecurity expert.

## Dataset

`eval/data/ground_truth.json` contains exactly 50 unique records:

| Topic | Questions |
|---|---:|
| Overview and applicability | 6 |
| Core and Functions | 8 |
| Profiles and Tiers | 8 |
| Resources and integration | 6 |
| Appendix A outcomes | 18 |
| Glossary | 4 |

Appendix A includes three questions for each CSF Function. Across the full set, 30
questions are direct, 15 require multiple claims, and 5 compare or synthesize evidence.
Every record includes a stable ID, reference answer, atomic claims, and exact evidence
with source, section, printed page, PDF page index, and text.

The dataset remains `draft`. Mechanical validation confirms schema, quotas, corpus and
index identity, page locations, exact evidence spans, uniqueness, and indexed evidence
coverage; it does not replace human review of semantic claim support.

## Commands

Prepare the pinned BERTScore model and verify the local Ollama models:

```bash
uv run --group eval python scripts/warm_models.py
```

Validate the dataset against the PDF and live one-document index:

```bash
uv run --group eval python -m eval.dataset
```

Run a one-question, unjudged smoke across all five default models:

```bash
uv run --group eval python -m eval.run --limit 1
```

Place `GROQ_API_KEY` in the ignored root `.env`, then run the complete comparison with
fresh judge calls:

```bash
uv run --group eval python -m eval.run --judge --no-cache
```

Use `--models` to select a subset, `--cosine-threshold` or `--bert-threshold` for an
explicit experimental threshold, and `--resume eval/results/<run-id>` to retry incomplete
rows with the same v2 configuration. Version-one runs cannot be resumed.

On a judged v2 resume, a row that already has its answer, cosine score, and BERTScore
reuses that work and retries only the missing judgment. If Groq's daily token quota
remains exhausted after the bounded retry budget, the runner atomically saves the row,
refreshes the partial reports, and stops before the next pair. Run the same resume command
after quota capacity returns; do not publish the partial aggregates.

## Outputs

Each ignored timestamped run under `eval/results/` writes:

- `config.json` with dataset, model, generation, retrieval, metric, and judge identity
- `results.jsonl` with complete question-model records and retrieved context
- `results.csv` with flattened question-level scores, judgments, latency, and errors
- `summary.csv` with one aggregate row per model
- `report.md` with independent metric summaries and diagnostics
- `manual_review.json` with a deterministic sample for human labeling

Technical failures remain visible on their question-model rows rather than becoming zero
scores. After the acceptance gate passes, the completed 250-row comparison is published
separately under `eval/final/` as `results.csv`, `summary.csv`, and `report.md`.

## Final results

Run `20260729T074749Z` completed all 250 question-model rows: 50 questions for each of
the five models, with all three metrics present and zero technical errors. The tables
below reproduce `report.md` at three-decimal precision; `summary.csv` retains the exact
aggregates.

| Model | Rows | Cosine mean | Cosine median | Cosine pass | BERT P | BERT R | BERT F1 | BERT F1 median | BERT pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `gemma2:2b` | 50 | 0.848 | 0.864 | 82% | 0.890 | 0.932 | 0.910 | 0.904 | 100% |
| `gemma4:e2b` | 50 | 0.840 | 0.853 | 76% | 0.880 | 0.933 | 0.905 | 0.901 | 98% |
| `llama3.2:latest` | 50 | 0.817 | 0.848 | 74% | 0.856 | 0.921 | 0.887 | 0.884 | 96% |
| `phi4-mini:latest` | 50 | 0.802 | 0.802 | 64% | 0.850 | 0.909 | 0.878 | 0.874 | 86% |
| `qwen2.5:1.5b` | 50 | 0.785 | 0.742 | 48% | 0.864 | 0.904 | 0.883 | 0.873 | 90% |

| Model | Correct | Complete | Faithful | Relevant | Judge pass | Partial | Fail |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma2:2b` | 3.680 | 3.680 | 3.680 | 3.820 | 90% | 4% | 6% |
| `gemma4:e2b` | 3.440 | 3.500 | 3.600 | 3.560 | 82% | 8% | 10% |
| `llama3.2:latest` | 3.200 | 3.200 | 3.340 | 3.420 | 76% | 10% | 14% |
| `phi4-mini:latest` | 2.420 | 2.460 | 2.500 | 2.880 | 50% | 14% | 36% |
| `qwen2.5:1.5b` | 2.040 | 2.000 | 2.180 | 2.400 | 44% | 10% | 46% |

| Model | Rewrite mean ms | Retrieval mean ms | Generation mean ms | Judge mean ms | Total mean ms | Total median ms | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma2:2b` | 0.018 | 168.321 | 2445.811 | 13607.658 | 16881.981 | 15476.825 | 0 |
| `gemma4:e2b` | 0.023 | 254.767 | 3293.657 | 11149.725 | 15864.783 | 15589.294 | 0 |
| `llama3.2:latest` | 0.016 | 177.714 | 3338.343 | 11446.828 | 15529.731 | 15536.840 | 0 |
| `phi4-mini:latest` | 0.043 | 235.092 | 4246.583 | 9056.066 | 14976.813 | 15121.344 | 0 |
| `qwen2.5:1.5b` | 0.021 | 343.347 | 1772.124 | 16143.447 | 19934.264 | 14984.969 | 0 |

Judgment collection resumed across multiple user-authorized Groq credentials and quota
windows. The provider, judge model `openai/gpt-oss-120b`, temperature `0`, prompt,
request policy, rubric, candidate models and digests, retrieval and generation settings,
and no-cache policy remained fixed. Credentials and organization identifiers are not
retained in the run artifacts; no account or service-tier equivalence is claimed. Quota
scheduling changed when judge calls ran, not the evaluation contract. Reported latencies
are per-row stage timings and do not include time between quota windows.

These are independent measurements, not a combined ranking. `gemma2:2b` had the highest
mean cosine, mean BERTScore F1, and judge pass rate in this run, but cosine and BERTScore
remain reference-similarity measures, and the LLM judge remains a review aid. The dataset
is still `draft`, contains only answerable single-turn CSF 2.0 questions, and measures
retrieval and generation together. Threshold calibration, unanswerable behavior,
conversation, and broader-corpus generalization remain outside this comparison.

## Limitations

The benchmark contains answerable, single-turn questions from one document. It does not
measure refusal behavior, unanswerable questions, conversational rewriting,
fixed-context generation, pairwise ranking, cross-document synthesis, or threshold
calibration. End-to-end scores combine retrieval and generation effects. Production
indexing, FastAPI, Streamlit, and chat remain local; only an explicit evaluation run with
`--judge` calls Groq.
