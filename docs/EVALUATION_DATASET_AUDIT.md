# Evaluation Dataset Audit

This audit records the repository and corpus state verified on 2026-07-28 before replacing
the legacy retrieval-focused evaluation harness. The legacy paths below are a snapshot of
the pre-replacement system, not current operational instructions. Approved version-one
evaluation behavior is specified separately in `docs/EVALUATION_PLAN.md`.

## Current pipeline

### Indexing

- `Pipeline.index()` is the indexing entry point. It discovers supported documents,
  parses and chunks changed files, embeds chunk text, updates Chroma, and rebuilds BM25
  when indexed content changes (`src/csrs/pipeline.py:104-210`).
- Discovery is recursive, sorted, and limited to registered PDF and TXT parsers
  (`src/csrs/loaders/__init__.py:23-48`). PDF parsing defaults to Docling and can be
  switched to the pypdf/pdfplumber fallback (`src/csrs/config.py:71-73`,
  `src/csrs/loaders/__init__.py:29-34`).
- The Streamlit entry point constructs and indexes a `Pipeline` through
  `load_pipeline()` (`src/csrs/app.py:11-18`). The FastAPI application constructs and
  indexes its shared pipeline lazily (`src/csrs/api/app.py:167-178`) and exposes
  incremental reload and full rebuild endpoints (`src/csrs/api/app.py:564-574`).

### Question paths and rewriting

- Non-streaming and streaming requests use `Pipeline.ask()` and `Pipeline.ask_stream()`
  respectively (`src/csrs/pipeline.py:234-346`). Their orchestration is duplicated, but
  both call the same `rewrite_query()`, `embed_query()`, `retrieve()`, and generation
  functions with the same retrieval settings.
- With no history, `rewrite_query()` returns the original question without calling Ollama.
  With history, it uses the last two turns and temperature `0.0`
  (`src/csrs/generation.py:45-74`).
- The candidate answer model is passed to `rewrite_query()`. A model comparison with
  conversational history can therefore change rewriting and retrieval as well as answer
  generation (`src/csrs/pipeline.py:243-259`, `src/csrs/pipeline.py:302-317`).
- Rewrite failures, empty output, and output longer than 300 characters fall back to the
  original question (`src/csrs/generation.py:75-93`). The original user question, not the
  rewritten search query, is sent to answer generation
  (`src/csrs/pipeline.py:279-290`, `src/csrs/pipeline.py:337-345`).

### Embeddings, retrieval, and context

- The configured embedding model is `nomic-embed-text` with dimension 768
  (`src/csrs/config.py:39-44`).
- Document embeddings use `search_document:` and query embeddings use `search_query:`
  (`src/csrs/embeddings.py:11-52`). These APIs are retrieval-asymmetric; the repository
  has no existing symmetric answer-similarity embedding function.
- Hybrid retrieval is the default. It retrieves 20 dense and 20 BM25 candidates, applies
  reciprocal rank fusion with `k=60`, and passes at most five chunks to generation by default.
  FlashRank support exists but is disabled (`src/csrs/config.py:79-90`,
  `src/csrs/pipeline.py:253-278`).
- RRF uses the sum of `1 / (k + rank)` and deterministic score/ID ordering
  (`src/csrs/retrieval.py:75-91`). Hybrid search preserves dense cosine and RRF scores,
  including a calculated cosine score for sparse-only results
  (`src/csrs/retrieval.py:249-299`).
- `RetrievedChunk` retains dense cosine score, zero-based rank, optional RRF score, and
  optional reranker score (`src/csrs/models.py:51-59`). Raw BM25 scores are used for the
  sparse ranking but are not copied into `RetrievedChunk`
  (`src/csrs/retrieval.py:207-226`, `src/csrs/retrieval.py:261-299`).
- The final `RetrievedChunk` objects are passed directly to generation. `Answer.sources`
  retains those exact objects, so an evaluation command can preserve the actual generator
  context without changing public application behavior (`src/csrs/generation.py:103-137`,
  `src/csrs/models.py:62-70`).
- There is no public retrieval-only `Pipeline` method. The existing evaluator calls
  `embed_query()` and `retrieve()` directly (`eval/run_eval.py:131-195`).

### Metadata, citations, configuration, and timing

- A chunk stores a deterministic positional ID, text, document basename, section breadcrumb,
  one-based physical PDF page, control ID, optional parent ID, and content hash
  (`src/csrs/models.py:18-37`, `src/csrs/chunking.py:218-245`).
- Chroma persists the same metadata except `None` values
  (`src/csrs/store.py:112-142`). Repository-relative source paths and printed page labels
  are not stored in chunks. Indexing rejects duplicate basenames across recursive
  directories (`src/csrs/pipeline.py:114-126`).
- The answer prompt labels passages `[S1]` through `[Sn]`, but it does not require generated
  citation markers (`src/csrs/generation.py:32-42`). FastAPI returns retrieved-source
  metadata and text separately (`src/csrs/api/app.py:429-440`); Streamlit displays only
  answer text and model (`src/csrs/app.py:147-160`).
- Answer generation configures `num_ctx`, temperature, and keep-alive only. The defaults are
  8192, `0.1`, and `30m` (`src/csrs/config.py:59-62`,
  `src/csrs/generation.py:103-129`). Seed, maximum output tokens, stop sequences, structured
  output, and thinking are not configured.
- The non-streaming API measures total request time only
  (`src/csrs/api/app.py:399-428`). The streaming API measures a combined
  rewrite/embedding/retrieval stage and a generation stage, not independent rewrite and
  retrieval times (`src/csrs/api/app.py:449-559`).
- `refusal_threshold` is declared but is not read by the runtime. Refusal currently occurs
  for empty context or when generated text matches the configured refusal message
  (`src/csrs/config.py:92-98`, `src/csrs/generation.py:96-137`).

## Legacy evaluation layer observed before replacement

- At audit time, `eval/golden_set.yaml` contained 48 retrieval-oriented pairs: 12 exact-ID,
  12 paraphrase,
  8 cross-document, 10 out-of-scope, and 6 specification examples.
- Its validator checks structure, provenance chunk IDs, and matchers against the live
  Chroma index (`eval/validate_golden_set.py:36-49`,
  `eval/validate_golden_set.py:109-242`).
- Existing pure metrics are Recall@k, reciprocal rank, nDCG@k, and refusal accuracy
  (`eval/metrics.py:16-135`).
- The runner can perform dense or hybrid retrieval and optional generation, but its
  per-question output stores ranked chunk IDs, ranking metrics, first relevant rank, and
  refusal state only. It does not store generated text, raw retrieved chunks and scores,
  reference answers, claims, evidence, cosine similarity, judge results, or phase latency
  (`eval/run_eval.py:131-212`, `eval/run_eval.py:379-404`).
- The legacy harness bypassed `Pipeline.ask()` and did not call query rewriting
  (`eval/run_eval.py:131-195`). Its single-turn questions therefore could not evaluate
  rewrite quality.
- At audit time the repository already depended on Pydantic, while the evaluation dependency
  group added only PyYAML and NumPy (`pyproject.toml:27-35`).

## Corpus manifest findings

The index manifest reports four documents and 2,506 chunks
(`chroma_db/manifest.json:1-22`). Direct extraction confirmed non-empty text on every page
of all three PDFs. Exact hashes and pagination notes are recorded in
`eval/data/corpus_manifest.json:1-41`.

| Repository source | Verified title and version | Pages | Extraction and pagination |
|---|---|---:|---|
| `docs/NIST.SP.1299.pdf` | *NIST Cybersecurity Framework 2.0: Resource & Overview Guide*, NIST SP 1299, February 2024 | 8 | All pages contain extractable text. The pages have no printed identifiers. |
| `docs/NIST.SP.800-53r5.pdf` | *Security and Privacy Controls for Information Systems and Organizations*, NIST SP 800-53 Revision 5, September 2020, updated 2020-12-10 | 492 | All pages contain extractable text. Cover, Roman preliminary, and Arabic body pagination require separate PDF indexes and printed labels. |
| `docs/samples/NIST.CSWP.29_CSF-2.0.pdf` | *The NIST Cybersecurity Framework (CSF) 2.0*, NIST CSWP 29, version 2.0, February 26, 2024 | 32 | All pages contain extractable text. The cover is unnumbered, preliminaries are i-iv, and the body is 1-27. |
| `docs/samples/OWASP_Top_10_2021.txt` | *OWASP Top 10:2021*, 2021 edition, v1.1 released July 13, 2025 | n/a | Direct UTF-8 text; no page numbering. |

`docs/README.md` is not part of the indexed corpus because `.md` is not a registered source
format (`src/csrs/loaders/__init__.py:23-40`).

## Ollama model inventory

The configured candidate names match the requested list exactly
(`src/csrs/config.py:50-57`). A later live `ollama list` check on 2026-07-28 confirmed all
five candidate generators and the embedding model. No model was substituted.

The following exact tags, manifest SHA-256 IDs, and model-layer digests were verified in the
local Ollama manifest and blob store under
`~/.ollama/models/manifests/registry.ollama.ai/library/`:

| Exact local tag | Manifest SHA-256 | Model-layer digest |
|---|---|---|
| `llama3.2:latest` | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` | `dde5aa3fc5ffc17176b5e8bdc82f587b24b2678c6c66101bf7da77af9f7ccdff` |
| `qwen2.5:1.5b` | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` | `183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4` |
| `gemma2:2b` | `8ccf136fdd5298f3ffe2d69862750ea7fb56555fa4d5b18c04e3fa4d82ee09d7` | `7462734796d67c40ecec2ca98eddf970e171dbb6b370e43fd633ee75b69abe1b` |
| `phi4-mini:latest` | `78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753` | `3c168af1dea0a414299c7d9077e100ac763370e5a98b3c53801a958a47f0a5db` |
| `gemma4:e2b` | `7fbdbf8f5e45a75bb122155ed546e765b4d9c53a1285f62fd9f506baa1c5a47e` | `4e30e2665218745ef463f722c0bf86be0cab6ee676320f1cfadf91e989107448` |
| `nomic-embed-text:latest` | `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f` | `970aa74c0a90ef7482477cf803618e776e173c007bf957f635f1015bfcfef0e6` |

The installed Ollama CLI reported version `0.32.1`. Its live `ID` column matched the first
12 hexadecimal characters of every manifest SHA-256 listed above:

```text
gemma4:e2b                 7fbdbf8f5e45
phi4-mini:latest           78fad5d182a7
gemma2:2b                  8ccf136fdd52
qwen2.5:1.5b               65ec06548149
llama3.2:latest            a80c4f17acd5
nomic-embed-text:latest    0a109f422b47
```

## Seed dataset

The audit produced 20 answerable draft records. The approved implementation converts that
seed into the human-readable `eval/data/ground_truth.json` used by the replacement evaluator:

| Source | Questions |
|---|---:|
| NIST CSWP 29 / CSF 2.0 | 5 |
| NIST SP 1299 | 4 |
| NIST SP 800-53 Revision 5 | 7 |
| OWASP Top 10:2021 | 4 |

Coverage is one definition, four requirements, eight lists, one numeric question, two
conditional questions, one exception/prohibition question, one comparison, and two other
guidance/outcome questions. Each record contains atomic required claims and exact extracted
evidence. The SP 1299 modality record keeps `must` and `should` as separate required claims.
Every record remains `draft` pending human review.

## EVAL-3 addendum — verified 2026-07-29

This addendum records the version-two CSF-only state. The 2026-07-28 sections above remain
the historical pre-replacement and version-one audit snapshot; they are not current
operational instructions.

### Corpus and live index

The supported corpus, `eval/data/corpus_manifest.json`, and live index now contain only
`docs/samples/NIST.CSWP.29_CSF-2.0.pdf`. Its identity is:

- Title: *The NIST Cybersecurity Framework (CSF) 2.0*
- Version: NIST CSWP 29, version 2.0, February 26, 2024
- SHA-256: `3c31f46fee98cac0c4323453e5109291a213b4de7fef8c058af9bf67f717433c`
- Pages: 32, with non-empty extracted text on every page
- Live index: 209 chunks for the same source hash and page count

The cover is unnumbered, preliminary pages use Roman numerals i–iv, and the body uses
printed pages 1–27. Dataset evidence therefore records the printed page separately from
the zero-based PDF page index.

### Dataset v2

`eval/data/ground_truth.json` is a version-two, `draft` dataset containing 50 entirely
new CSF-only questions. Its enforced topic quotas are:

| Topic | Questions |
|---|---:|
| Overview and applicability | 6 |
| Core and Functions | 8 |
| Profiles and Tiers | 8 |
| Resources and integration | 6 |
| Appendix A outcomes | 18 |
| Glossary | 4 |

The Appendix A group contains three questions for each of GOVERN, IDENTIFY, PROTECT,
DETECT, RESPOND, and RECOVER. The complete set contains 30 direct questions, 15
multi-claim questions, and 5 comparison or synthesis questions.

Each question stores a stable ID, topic, question type, question text, primary reference
answer, optional acceptable answers, one or more atomic claims, and one or more exact
evidence records. Each evidence record stores the CSF source path, section, printed page,
zero-based PDF page index, and source text.

The validator requires exactly 50 unique and non-near-duplicate questions, the fixed
topic/type/Function quotas, CSF-only evidence, valid sections and pages, exact normalized
evidence spans in the PDF, corpus-manifest/filesystem/live-index identity, and evidence
tokens represented in indexed chunks. These checks are mechanical; semantic claim
support remains `draft` pending human review.

### Evaluation contract

All five configured Ollama generators are defaults:

- `llama3.2:latest`
- `qwen2.5:1.5b`
- `gemma2:2b`
- `phi4-mini:latest`
- `gemma4:e2b`

Every model uses temperature `0`, seed `42`, context size `8192`, maximum output
`512` tokens, disabled thinking, and no custom stop sequence. Retrieval returns ten
chunks and supplies the first five to generation and the judge.

The version-two result contract contains exactly three independent metric objects:

1. Cosine similarity from local `nomic-embed-text:latest` embeddings with the symmetric
   `clustering:` prefix and fixed pass threshold `>= 0.75`.
2. Raw BERTScore precision, recall, and F1 from the pinned
   `FacebookAI/roberta-large` revision
   `722cf37b1afa9454edce342e7895e588b6ff1d59`, layer 17, CPU, no IDF, and no baseline
   rescaling. The pass threshold is `F1 >= 0.85`.
3. An optional Groq `openai/gpt-oss-120b` judge at temperature `0`, scoring correctness,
   completeness, faithfulness, and relevance from 0 to 4 and returning a structured
   verdict and diagnostics.

Accepted alternative references are scored independently; cosine retains the highest
similarity and BERTScore retains the full precision/recall/F1 tuple associated with the
highest F1. Retrieval evidence hit/recall is no longer a reported metric. Gold evidence
and retrieved chunks remain in row-level records for judge grounding and diagnostics.
The three metrics are reported independently, with no combined score or overall pass.

Incomplete or failed question-model rows are replaced atomically on resume. A judged row
is technically complete only when it contains a generated answer, all three metric
objects, and no errors. Version-one configurations are incompatible with v2 resume.

### Final comparison status

The final 50-question by five-model judged comparison is pending. No aggregate scores are
recorded in this addendum until all 250 rows satisfy the technical-completeness contract.
The completed run will publish a detailed CSV, five-row summary CSV, and Markdown report
under `eval/final/`.
