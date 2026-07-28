# Evaluation Layer and Final Results

This directory contains a deliberately small end-to-end evaluation of the local RAG
assistant. It uses 20 draft questions whose answers and evidence come directly from the
four indexed cybersecurity documents.

The completed comparison evaluated `llama3.2:latest` and `qwen2.5:1.5b` on the same
questions, retrieval settings, five-chunk generator context, prompt, and generation
settings. The exact local run is in `eval/results/20260728T113753Z/`.

## The three techniques in simple terms

### 1. Answer cosine similarity

The evaluator converts the generated answer and correct reference answer into local
embedding vectors, then measures how closely their meanings point in the same direction.

- A higher value means the wording and meaning are more similar.
- The current `0.75` pass threshold is provisional, not calibrated.
- A high score does not prove that numbers, negation, control IDs, or MUST/SHOULD wording
  are correct. That is why cosine remains separate from the judge.

### 2. Retrieval evidence coverage

Before judging the answer, the evaluator checks whether retrieval actually found the gold
source passage.

- `hit@5` asks whether any gold evidence appeared in the five chunks given to the model.
- `recall@5` asks what fraction of all required evidence passages appeared there.
- The same checks at 10 diagnose whether evidence was retrieved but ranked below the
  generator's five-chunk context boundary.

This layer separates a retrieval failure from a generation failure. If the evidence was
missing, the generator never had a fair chance to use it.

### 3. Groq LLM judge

The fixed judge `openai/gpt-oss-120b` receives the question, candidate answer, reference,
atomic claims, gold evidence, and the five chunks supplied to the generator. It does not
receive the candidate model name.

It scores correctness, completeness, faithfulness, and relevance from 0 to 4 and records
missing claims, unsupported additions, contradictions, and a pass/partial/fail verdict.
The response is strict JSON, cached, and retained for audit. The judge is a consistent
review aid, not a replacement for a cybersecurity expert.

## Final two-model results

| Metric | `llama3.2:latest` | `qwen2.5:1.5b` |
|---|---:|---:|
| Questions | 20 | 20 |
| Mean cosine similarity | 0.897 | 0.792 |
| Median cosine similarity | 0.913 | 0.744 |
| Provisional cosine pass rate | 100% | 50% |
| Judge correctness (0–4) | 3.10 | 1.75 |
| Judge completeness (0–4) | 2.90 | 1.80 |
| Judge faithfulness (0–4) | 3.45 | 1.95 |
| Judge relevance (0–4) | 3.60 | 1.80 |
| Judge pass / partial / fail | 60% / 25% / 15% | 40% / 5% / 55% |
| Evidence hit / recall at 5 | 95% / 95% | 95% / 95% |
| Evidence hit / recall at 10 | 95% / 95% | 95% / 95% |
| Mean generation latency | 4.49 s | 2.66 s |
| Technical pipeline or API errors | 0 | 0 |

`llama3.2:latest` produced substantially stronger answers under both cosine and the
evidence-aware judge, while `qwen2.5:1.5b` was about 1.8 seconds faster on the mean
generation time. Retrieval scores are identical because both models used the same
standalone questions and retrieval configuration; the conversational rewriter was not
invoked.

The one shared retrieval miss was `sp1299-backup-actions`. The other low-quality answers
mostly had relevant evidence available, so those failures are attributable to generation
rather than retrieval.

## Commands

Validate the readable dataset:

```bash
uv run --group eval python -m eval.dataset
```

Run the default two-model comparison locally:

```bash
uv run --group eval python -m eval.run
```

Enable the Groq judge only after placing `GROQ_API_KEY` in the ignored root `.env`:

```bash
uv run --group eval python -m eval.run --judge
```

Use `--limit 1` for a fast smoke test. Other installed application models remain
selectable with `--models`, but they were intentionally excluded from this final run.

## Outputs and cautions

Each run writes `config.json`, `results.jsonl`, `summary.csv`, `report.md`, and
`manual_review.json`. Errors remain attached to their question rows rather than being
turned into zero scores.

The QA records are still marked `draft`. Manually review a representative answer sample
before treating `0.75` as a pass policy or treating the Groq verdict as a grading rule.
Normal FastAPI, Streamlit, indexing, and chat paths never call Groq and remain fully local.
