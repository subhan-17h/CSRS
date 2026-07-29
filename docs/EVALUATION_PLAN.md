# CSF-Only Three-Metric RAG Evaluation Plan

## Purpose and scope

The evaluator measures end-to-end answers to 50 single-turn questions grounded only in
`docs/samples/NIST.CSWP.29_CSF-2.0.pdf`. It compares all five installed Ollama answer
models under identical generation and retrieval settings:

- `llama3.2:latest`
- `qwen2.5:1.5b`
- `gemma2:2b`
- `phi4-mini:latest`
- `gemma4:e2b`

The three reported metrics are answer cosine similarity, raw BERTScore, and an optional
Groq LLM judgment. They remain independent; there is no aggregate score or overall pass.
Production indexing, FastAPI, Streamlit, and chat remain local. Only an explicit
evaluation command with `--judge` calls Groq.

## Dataset contract

`eval/data/ground_truth.json` is readable, versioned JSON. Each record contains a stable
ID, question, reference answer, optional acceptable alternatives, atomic required claims,
and exact evidence with source path, section, printed page, PDF page index, and text.

The 50 records use these fixed topic quotas:

| Topic | Questions |
|---|---:|
| Overview and applicability | 6 |
| Core and Functions | 8 |
| Profiles and Tiers | 8 |
| Resources and integration | 6 |
| Appendix A outcomes | 18 |
| Glossary | 4 |

Appendix A contains three questions for each of GOVERN, IDENTIFY, PROTECT, DETECT,
RESPOND, and RECOVER. Across all topics, 30 questions are direct, 15 require multiple
claims, and 5 compare or synthesize evidence. The records remain `draft` because exact
evidence validation is not a substitute for human cybersecurity review.

Validation rejects a dataset unless it contains exactly 50 unique questions, matches the
one-document corpus manifest and live index, uses valid pages, traces every evidence span
to the PDF, and covers every claim with evidence tokens represented in indexed chunks.

## Fixed evaluation configuration

Each answer model uses temperature `0`, seed `42` where supported, `num_ctx=8192`,
`num_predict=512`, thinking disabled, and no custom stop sequence. Retrieval returns ten
chunks and the first five are supplied to generation and the judge.

Cosine similarity embeds the candidate and accepted references with local
`nomic-embed-text:latest` using the symmetric `clustering:` task prefix. The evaluator
retains the highest reference score and applies the fixed `>= 0.75` pass threshold.

BERTScore uses `bert-score==0.3.13` with the pinned
`FacebookAI/roberta-large` snapshot
`722cf37b1afa9454edce342e7895e588b6ff1d59`, layer 17, CPU, no IDF, and no baseline
rescaling. It retains precision, recall, and F1 from the accepted reference with the
highest F1 and applies the fixed `F1 >= 0.85` pass threshold. The model is downloaded
once by the warm-model command and reused from the local Hugging Face cache.

The Groq judge uses `openai/gpt-oss-120b`, temperature `0`, low reasoning effort,
hidden reasoning, a versioned prompt, and strict JSON. It receives the question,
candidate and reference answers, atomic claims, gold evidence, and the five chunks
supplied to generation. Candidate-model identity is hidden.

The fixed judge rubric scores correctness, completeness, faithfulness, and relevance
from 0 to 4 and records a `pass | partial | fail` verdict, missing claim IDs, unsupported
claims, and contradictions. One invalid structured response gets one repair request.
Transient transport, rate-limit, and server errors use bounded retries.

## Result and resume contracts

Each question-model row records schema/run/dataset identity, exact model tag and digest,
generation settings, rewritten query, ten retrieved chunks, the generated and reference
answers, gold claims and evidence, phase latency, the three metric objects, and visible
errors.

Resume identity includes the dataset hash, model digests, thresholds, generation,
retrieval, BERTScore, and judge configuration. A row is complete only when it contains a
generated answer plus cosine, BERTScore, and a valid judgment when judging is enabled.
Incomplete rows are replaced atomically on resume. Version-one runs are not resumable
under the version-two contract.

Successful judge cache identity covers all judgment inputs and fixed request settings.
The final comparison bypasses that cache so all 250 judgments are fresh.

Each timestamped run writes:

- `config.json`
- `results.jsonl`
- `results.csv`
- `summary.csv`
- `report.md`
- `manual_review.json`

Once the acceptance gate passes, the tracked `eval/final/` directory will contain only
the completed run's detailed CSV, five-row summary CSV, and Markdown report. The detailed
CSV omits bulky retrieved chunks and raw judge JSON but retains answer text, component
scores, judge explanations and issue lists, latency, and errors.

## Reporting policy and limitations

Per-model reports include question and successful-answer counts; cosine mean, median,
and pass rate; BERTScore precision, recall, and F1 means plus F1 median and pass rate;
judge criterion means and verdict rates; generation latency; and technical failures.

Cosine and BERTScore measure semantic agreement, not factual correctness. They can miss
incorrect numbers, negation, modality, exceptions, or required list items. The LLM judge
is a consistent rubric-based aid, not an expert. Raw structured judgments and a
deterministic manual-review sample remain available in the ignored run directory.

The benchmark is answerable and single-turn. It does not measure refusal behavior,
unanswerable questions, conversational rewriting, fixed-context generation, pairwise
ranking, or threshold calibration. End-to-end results combine retrieval and generation
effects.

## Acceptance criteria

The evaluation is complete only when:

1. The filesystem, corpus manifest, Chroma, and BM25 contain one 32-page CSF document
   and 209 chunks.
2. All 50 questions validate against the PDF and live index.
3. All five exact Ollama tags run the same fixed configuration.
4. The final judged run contains exactly 250 technically complete rows with all three
   metrics and no pipeline or API errors.
5. The tracked detailed CSV has 250 rows, the summary CSV has five rows, and the
   Markdown report identifies the same completed run and thresholds.
6. Focused tests, offline regression tests, Ruff, Python ASCII validation, and
   `git diff --check` pass.
