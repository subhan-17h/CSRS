# Minimal Three-Layer RAG Evaluation Plan

## Purpose and approved scope

Version one replaces the legacy 48-question retrieval harness with one end-to-end evaluator
over the 20 evidence-grounded, human-readable questions in
`eval/data/ground_truth.json`. The completed comparison uses two approved Ollama generators
without an aggregate score:

- Answer cosine similarity with local `nomic-embed-text:latest`.
- Evidence hit and recall at 5 and 10.
- Optional Groq LLM judging with `openai/gpt-oss-120b`.

Production indexing, FastAPI, Streamlit, and chat remain fully local. Groq is reachable only
from an explicit developer evaluation command.

## Verified architecture

- `Pipeline.index()` builds the recursive PDF/TXT corpus, Chroma vectors, and BM25 index.
- Query rewriting is skipped for standalone questions. With history, the selected candidate
  generator also rewrites, so generation-model changes can affect retrieval.
- Hybrid retrieval combines 20 dense and 20 BM25 candidates through RRF with `k=60`; the
  production generator normally receives five chunks.
- Document embeddings use `search_document:` and retrieval queries use `search_query:`.
  Those asymmetric APIs are not reused for answer similarity.
- Retrieved chunks retain rank, dense score, RRF score, and source metadata, but not raw
  BM25 score. The evaluator can preserve generator context without changing public APIs.
- All four corpus sources have usable text. Live Ollama inventory confirms the five
  candidate tags and `nomic-embed-text:latest`; exact digests are in the dataset audit.

## Approved decisions

- Keep exactly 20 answerable, single-turn questions with `draft` review status. Do not add
  unanswerable questions or expand the dataset before human review.
- Use end-to-end comparison only. Fixed-context generation and conversational rewrite
  evaluation are deferred.
- Compare `llama3.2:latest` and `qwen2.5:1.5b` without tag substitution. Keep the other
  three installed application models selectable for later runs.
- Retrieve ten chunks, pass the first five to generation, and report evidence hit and recall
  at both depths.
- Embed the candidate and every accepted reference with the same symmetric `clustering:`
  prefix. Keep the maximum cosine score and selected reference. Use `0.75` only as a
  configurable, explicitly uncalibrated provisional threshold.
- Make Groq judging opt-in. Judge correctness, completeness, faithfulness, and relevance on
  a 0-4 rubric; also retain missing claims, unsupported claims, contradictions, and the
  `pass | partial | fail` verdict.
- Give the judge the question, candidate and reference answers, atomic claims, gold
  evidence, and the five chunks actually supplied to generation. Hide candidate-model
  identity and never request private reasoning.
- Use one cached judge call per answer, strict structured output, and one controlled repair
  attempt. Fail visibly after invalid output.
- Fix model-comparison settings at temperature `0`, seed `42` where supported,
  `num_ctx=8192`, `num_predict=512`, no custom stop sequence, and consistent disabled
  thinking where supported.
- Export JSONL diagnostic records, a CSV model summary, a Markdown report, captured
  configuration, and a deterministic manual-review sample.

## Dataset and result contracts

The readable JSON dataset centralizes document titles and versions in
`eval/data/corpus_manifest.json`. Each question keeps only its stable ID, question, answer,
optional accepted alternatives, atomic claims, and exact evidence path/page/section/text.
Validation rejects duplicate IDs or questions, empty claims or evidence, invalid source
locations, and evidence that cannot be traced to the corpus.

Conceptually, each question has this minimal shape:

```json
{
  "id": "stable-id",
  "question": "Question text",
  "answer": "Reference answer",
  "acceptable_answers": [],
  "claims": [{"id": "claim-1", "text": "Atomic required fact"}],
  "evidence": [{
    "document_path": "docs/source.pdf",
    "section": "Exact section or null",
    "printed_page": "Printed label or null",
    "pdf_page_index": 0,
    "text": "Exact supporting passage"
  }]
}
```

Each question-model result retains the run and dataset IDs, exact candidate tag and digest,
fixed generation settings, rewritten query, ten ranked chunks, the five generator chunks,
generated and reference answers, rewrite/retrieval/generation/judge/total latency, all three
metric layers, raw validated judgment, and visible errors.

## Command and outputs

The primary interface is:

```bash
uv run --group eval python -m eval.run --models \
  llama3.2:latest qwen2.5:1.5b
```

`--judge` explicitly enables Groq. The command also supports dataset/model selection,
question limits, cosine threshold, output directory, cache bypass, and resume. A run writes
`config.json`, `results.jsonl`, `summary.csv`, `report.md`, and `manual_review.json`.
Errors remain attached to their question result rather than becoming success-shaped scores.

## Judge and metric policy

Cosine similarity measures semantic agreement, not factual correctness. It preserves
negation, numbers, control identifiers, versions, and modality. Empty answers, malformed
vectors, and zero-norm vectors are errors.

Evidence matching uses source basename, physical page where present, and at least 90%
normalized evidence-token coverage. Answer cosine similarity is never used as retrieval
relevance.

The Groq judge uses environment variable `GROQ_API_KEY`, model
`openai/gpt-oss-120b`, temperature `0`, low reasoning effort, a versioned prompt, and strict
JSON validation. Cache identity includes question ID, answer hash, context hash, judge
model, prompt version, and prompt hash. Reports keep the raw structured judgment, provider,
model, prompt version, and prompt hash without logging credentials.

The fixed judge rubric is:

- `4`: fully satisfies the criterion.
- `3`: substantially correct with only a minor omission or issue.
- `2`: partially correct with material omissions or unsupported details.
- `1`: mostly incorrect with a small amount of correct information.
- `0`: incorrect, contradictory, unsupported, or non-responsive.

Correctness is measured against the reference and claims; completeness is required-claim
coverage; faithfulness is support from gold evidence and supplied context; relevance is
responsiveness to the question. Incorrect numbers, conditions, control IDs, versions,
modality, exceptions, and missing list items are substantive errors. The response records
0-4 criterion scores, concise evidence-based justifications, missing claim IDs, unsupported
and contradicted claims, and `pass | partial | fail`.

Per-model reports include question count; cosine mean, median, and provisional-threshold
rate; judge criterion averages and verdict rates; evidence hit and recall at 5 and 10;
generation-latency mean and median; failures; dataset/config versions; and a question-level
error table. No weighted aggregate is emitted.

## Implementation phases

### Phase 1: replace data and legacy code

- **Goal:** establish one readable, corpus-grounded benchmark and remove the obsolete
  operational harness.
- **Scope/files:** replace legacy evaluator files under `eval/`, add
  `eval/data/ground_truth.json`, retain the corpus manifest, and update operational docs.
- **Deliverable:** the 20-question JSON loads through the compact schema; no current command
  references deleted YAML or scripts.
- **Verification/completion:** validate JSON, duplicates, manifest hashes/page counts, and
  every evidence span against the corpus and indexed metadata.

### Phase 2: implement metrics and optional judge

- **Goal:** produce three independent, auditable evaluation layers.
- **Scope/files:** dataset loader, metric functions, Groq judge/cache, and one versioned
  judge prompt under `eval/`; add Groq only to the evaluation dependency group.
- **Deliverable:** cosine result with selected reference, evidence metrics at 5/10, and
  opt-in validated judge output.
- **Verification/completion:** focused unit tests cover normal cases, empty/zero vectors,
  multiple references, source/page evidence mismatches, invalid judge output, repair, and
  stable cache keys without a paid API call.

### Phase 3: implement end-to-end running and reports

- **Goal:** compare the two approved local generators fairly and preserve failure provenance.
- **Scope/files:** orchestration and reporting modules under `eval/`.
- **Deliverable:** the primary CLI and five output artifacts, with resumable cached work and
  phase latency.
- **Verification/completion:** a one-question unjudged smoke run preserves ten retrieved
  chunks, five generator chunks, an answer, metrics, configuration, and reports.

### Phase 4: integration verification

- **Goal:** prove evaluation is isolated from the production offline path.
- **Scope/files:** focused evaluation tests and concise current documentation.
- **Deliverable:** mocked judge coverage, production regression evidence, and reproducible
  commands.
- **Verification/completion:** one judged smoke after the user supplies a key, then the full
  comparison; existing offline tests, Ruff, ASCII-only Python, and `git diff --check` pass.

## Rejected and deferred alternatives

- No weighted overall score, deterministic answer-check layer, MRR, nDCG, refusal metric,
  generated inline-citation requirement, repeated judging, or pairwise model ranking.
- No dashboard, database, generic provider abstraction, distributed workers, evaluation
  framework, CI integration, or production refactor.
- No fixed-context mode, multi-turn benchmark, unanswerable set, or calibrated pass
  threshold in version one.
- No automatic model downloads or model substitutions.

## Acceptance criteria and known limitations

- Version one is complete when all 20 questions validate against actual corpus evidence; both
  exact candidate tags run the same prompt/settings; results preserve answers,
  chunks, timings, metrics, judge audit data, and errors; JSONL/CSV/Markdown/manual review
  exports are generated; and production code never imports or calls Groq.
- The questions remain `draft` until a person reviews their claims and evidence. Review
  roughly 30-50 representative generated answers before calibrating cosine or judge pass
  thresholds.
- Cosine similarity tolerates paraphrase but does not prove factual correctness, complete
  claim coverage, correct numbers, negation, or modality.
- The LLM judge can be inconsistent or biased and is not expert human review. Candidate
  names are hidden, one rubric/prompt is fixed, raw judgments are retained, and a manually
  reviewed subset is required for calibration.
- End-to-end results combine retrieval and generation effects. The single-turn dataset does
  not exercise the model-coupled conversational rewriter.
