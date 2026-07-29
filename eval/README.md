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

**Pending final run.** This section will be updated only after all 250 question-model
rows contain cosine similarity, BERTScore, and LLM-judge results with no technical
errors. No scores are reported before that acceptance condition is demonstrated.

## Limitations

The benchmark contains answerable, single-turn questions from one document. It does not
measure refusal behavior, unanswerable questions, conversational rewriting,
fixed-context generation, pairwise ranking, cross-document synthesis, or threshold
calibration. End-to-end scores combine retrieval and generation effects. Production
indexing, FastAPI, Streamlit, and chat remain local; only an explicit evaluation run with
`--judge` calls Groq.
