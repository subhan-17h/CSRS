# Submission — Cybersecurity Standards RAG System

This document explains what I built, which requirement each piece satisfies, and how the
system actually works — including the reasoning behind each decision and the measurements
that drove it. [README.md](README.md) is how to run it. This is the walkthrough.

---

## 1. What this is

A question-answering system over cybersecurity standards. You ask a question in plain
English, it finds the relevant passages in the loaded documents, and a local language model
writes an answer from **only those passages**. Nothing leaves the machine — the language
models, the embedding model and the vector database all run locally.

```
question -> nomic-embed-text -> Chroma (cosine) ---\
                                                    >-- RRF fusion -> top 5 -> llama3.2 -> grounded answer
question -> BM25 (bm25s) --------------------------/
```

Currently indexed: **4 documents, 2506 chunks, 532 pages.**

---

## 2. Requirements checklist

Every row maps a line from [CSRS.md](CSRS.md) to the code that satisfies it.

### Section 1 — Document Management

| Requirement | Where | How |
|---|---|---|
| Accept PDF and TXT | `loaders/__init__.py:29` | `get_parser()` routes `.pdf` to Docling (or pypdf) and `.txt` to `TextParser` |
| Auto-load every document from `docs/` | `loaders/__init__.py:37` | `iter_document_paths()` walks `docs/` recursively with `rglob`, including subfolders |
| Support multiple documents | `pipeline.py:124` | The index loop runs over every discovered file; 4 are indexed today |
| Detect new documents, no code change | `pipeline.py:125-131` | Each file's SHA-256 is compared against `chroma_db/manifest.json`. A new file has no manifest entry, so it is parsed and indexed |
| "Restart & Reload Documents" button | `app.py:122`, `api/app.py:508` | Streamlit button; React button posting to `POST /api/index/reload` |
| Extensible to new standards | — | Drop a `.pdf` or `.txt` into `docs/`, press reload. No configuration, no restart |

### Section 2 — Knowledge Base Construction

| Requirement | Where | How |
|---|---|---|
| Read PDF and TXT files | `loaders/docling_parser.py`, `loaders/text.py` | Docling runs a document-layout model over the PDF; TXT is read as UTF-8 with replacement on bad bytes |
| Extract document text | `docling_parser.py:69` | Exported as Markdown with a unique page-break placeholder, then split so every chunk keeps its page number |
| Split into meaningful chunks | `chunking.py:218` | Structure-aware: splits on headings first, then recursively on paragraph, line, sentence, word |
| Generate embeddings for every chunk | `embeddings.py:36` | `embed_documents()`, batches of 32, through Ollama |
| Store in a local vector store | `store.py:112` | Chroma `PersistentClient` writing to `chroma_db/` |
| Embedding happens automatically on load/reload | `api/app.py:160`, `app.py:17` | Both interfaces call `pipeline.index()` on startup and on every reload |

### Section 3 — Semantic Retrieval

| Requirement | Where | How |
|---|---|---|
| Embed the user's query | `embeddings.py:49` | `embed_query()` with the `search_query:` prefix |
| Retrieve by semantic similarity | `store.py:144` | Chroma cosine search; the returned distance is converted to a similarity score with `1.0 - distance` |
| Supply **only** retrieved context to the model | `generation.py:31` | `build_prompt()` places only the retrieved chunks under `CONTEXT`. The model receives nothing else about the corpus |
| Keyword search alone is not sufficient | `retrieval.py:338` | Semantic retrieval is the base, and keyword search is *fused into* it rather than replacing it. Asking *"what must an organization do for automated system account management?"* retrieves control `AC-2(1)` at 0.8420 without sharing those words with the source text — that is the dense half doing work BM25 cannot. The measured converse is section 8: BM25 is what takes exact control-ID lookup from 0.896 MRR to a perfect 1.000 |

### Section 4 — Question Answering

| Requirement | Where | How |
|---|---|---|
| Answer using retrieved context | `generation.py:51` | The prompt is `CONTEXT` / `QUESTION` / `INSTRUCTION`, in that order |
| Avoid inventing information | `generation.py:37-40` | The instruction is explicit: *"Answer using only the context above."* Temperature is 0.1 |
| Say so when information is not found | `generation.py:44` | The model is told to reply with an exact refusal sentence. `_is_refusal()` detects it and sets `Answer.refused = True` |
| Preserve conversational context (**bonus**) | — | **Not built.** See section 10 |

### Section 5 — User Interface (Streamlit)

| Requirement | Where |
|---|---|
| Question input box | `app.py:147` |
| Generated answer | `app.py:159`, with the answering model named underneath |
| Loaded document list | `app.py:105-118` — filename, chunk count, page count |
| Current model selection | `app.py:82` — `st.selectbox` populated from what Ollama actually has installed |
| Restart & Reload Documents button | `app.py:122` |
| Sidebar with application settings | `app.py:63` — Ollama status, model, `top_k`, temperature |

A second interface (React + FastAPI) was built on top of the same pipeline. Streamlit is the
one the specification asks for and it is fully intact; the web UI adds citations, streaming
and a corpus browser. Both are described in the README.

### Section 6 — Local LLM Integration

| Requirement | Where | How |
|---|---|---|
| Must use Ollama | `embeddings.py:14`, `generation.py:19` | These two lines are the only network clients in the codebase. There is no HTTP client for any cloud provider anywhere in the source |
| `nomic-embed-text` mandatory for embeddings | `config.py:42` | Hard default, with a comment warning that changing it also breaks the task prefixes |
| Five supported LLMs | `config.py:51-57` | `llama3.2`, `qwen2.5:1.5b`, `gemma2:2b`, `phi4-mini`, `gemma4:e2b` |
| Selectable from a dropdown | `app.py:82`, `api/app.py:341` | The list is filtered against what Ollama reports as installed, so you cannot select a model that would fail |

### Deliverables

| Asked for | Provided |
|---|---|
| Complete source code | `src/csrs/` (2696 lines), `frontend/` (4112 lines), `tests/` (205 passing offline) |
| README with install / setup / adding documents / running | [README.md](README.md) |
| `requirements.txt` or `pyproject.toml` | [pyproject.toml](pyproject.toml) plus `uv.lock` for byte-reproducible installs |
| Sample cybersecurity documents | `docs/samples/` — one PDF and one TXT, committed |

---

## 3. How a question gets answered

Seven steps, from typing to answer. The entry point is `Pipeline.ask()` at `pipeline.py:179`.

1. **Empty-index guard.** If nothing is indexed, refuse immediately rather than asking a
   model about an empty corpus.
2. **Embed the question.** `embed_query()` sends it to `nomic-embed-text` with the
   `search_query:` prefix and gets back a 768-dimension vector. That prefix matters: Nomic
   was trained with different prefixes for stored text and search text, and mixing them up
   silently degrades results without erroring.
3. **Retrieve.** `retrieve()` in `retrieval.py` is the single composition point. By default
   it runs **hybrid** retrieval: Chroma returns the 20 nearest chunks by cosine distance,
   a BM25 index returns its own top 20, and the two ranked lists are merged by reciprocal
   rank fusion — `RRF(d) = Σ 1/(k + rank_i(d))` with `k=60`. RRF uses *ranks only*, which
   is the point: cosine similarities and BM25 scores are on incomparable scales, and fusing
   by rank sidesteps calibration entirely. Setting `CSRS_RETRIEVAL_MODE=dense` skips the
   sparse half.
4. **Convert distance to similarity.** Chroma returns a distance; `1.0 - distance` gives the
   cosine similarity actually shown in the UI. Each result carries its chunk text plus the
   metadata stored with it: document name, page, section breadcrumb, control ID. A chunk
   found only by BM25 still gets a real cosine, computed from its stored embedding, so the
   score in the UI never changes meaning depending on how the chunk was found.
5. **Build the prompt.** `build_prompt()` wraps each chunk as `[S1]...[/S1]`, then appends
   the question, then the grounding instruction. The order is deliberate — the instruction
   is last so it is the most recent thing in the model's context.
6. **Generate.** `ollama.chat()` with `num_ctx=8192`, `temperature=0.1`, and
   `keep_alive=30m` so the model stays in memory between questions.
7. **Detect refusal and return.** `_is_refusal()` compares the answer against the configured
   refusal sentence, ignoring case, trailing whitespace and a trailing period. The result is
   an `Answer` object carrying the text, the refusal flag, the model name, and every source
   chunk used.

`ask_stream()` at `pipeline.py:216` is the same seven steps, except step 6 yields tokens as
they arrive so the web UI can display the answer as it is written.

---

## 4. How a document gets indexed

`Pipeline.index()` at `pipeline.py:79`.

1. **Discover.** Walk `docs/` recursively for supported extensions.
2. **Reject duplicate filenames.** Two files with the same basename in different folders
   would collide in the store, so this fails loudly instead of indexing one over the other.
3. **Consistency check.** If the manifest and the store disagree about chunk counts, the
   index is considered corrupt and rebuilt from scratch. This is what protects against a
   process killed halfway through an index run.
4. **Hash gate — the important step.** For each file, hash its bytes with SHA-256 and
   compare against the manifest. If it matches, skip the file **without opening it**. This
   is why an unchanged corpus reloads in 0.057 s instead of 316 s.
5. **Parse.** Docling converts the PDF to Markdown while tracking page boundaries. Running
   headers and footers are classified as page furniture by the layout model and dropped.
6. **Chunk.** `chunk_document()` splits at heading boundaries first, so a chunk rarely spans
   two unrelated controls. Each chunk records its page, its section breadcrumb, and its
   control ID.
7. **Embed and store.** Batches of 32 through `nomic-embed-text`, written into Chroma with
   their metadata.
8. **Update the manifest.** Written atomically via a temp file and `rename`, so a crash
   mid-write cannot leave a half-written manifest.

Deleted files have their chunks removed and their manifest entry dropped in the same pass.

---

## 5. Component reference

| Module | What it does | The non-obvious part |
|---|---|---|
| `config.py` | Every tunable in one typed class | Any setting can be overridden by a `CSRS_`-prefixed environment variable or a `.env` file, with no code change |
| `models.py` | The data contracts: `Chunk`, `Document`, `RetrievedChunk`, `Answer` | `Chunk.embed_text` prepends the section breadcrumb **only for embedding**. The stored text stays clean, so citations show the real passage while the vector carries the extra context |
| `loaders/` | `DoclingParser`, `PdfParser`, `TextParser` behind one `DocumentParser` protocol | Adding a new format means adding one class; nothing that calls it changes |
| `chunking.py` | Structure-aware splitting | Maintains a heading stack while walking the document, so it knows which control a paragraph belongs to. A bare `(1)` enhancement heading resolves against the nearest control on that stack and becomes `AC-2(1)` |
| `embeddings.py` | The only module that talks to the embedding model | Owns the `search_document:` / `search_query:` prefixes, and validates that every returned vector is 768-dimensional before it is stored |
| `store.py` | Chroma persistence, the manifest, and dense search | Also owns `file_content_hash()` — the SHA-256 that makes reloads incremental |
| `retrieval.py` | The BM25 index, RRF fusion, reranking, and the one `retrieve()` both interfaces reach | The BM25 tokenizer is pinned to `(?u)\b\w[\w-]*\b`. `bm25s`'s default splits on the hyphen, collapsing `AC-2` and `AC-3` to the token `ac` — which would silently destroy the exact-ID lookup that BM25 was added for |
| `generation.py` | Prompt assembly, generation, refusal detection | The refusal check is exact-match by design. A fuzzy matcher would misclassify legitimate answers that happen to hedge, which is a worse failure than under-counting refusals |
| `pipeline.py` | The single facade both interfaces call | Neither UI imports Chroma or Ollama. This boundary is what allowed a second interface to be added without touching retrieval or generation |
| `app.py` | Streamlit interface | 164 lines, because all the work is behind the facade |
| `api/app.py` | FastAPI — chat, streaming, index control, corpus browsing, static hosting | Index operations run in a worker thread and stream NDJSON progress, so the browser shows what is happening during a five-minute rebuild instead of hanging |
| `frontend/` | React 18 + TypeScript + Vite | Fonts are vendored as local `.woff2` files. An imported component fetched them from a CDN, which broke the offline requirement, so they were pulled in |

---

## 6. Configuration

Everything lives in `src/csrs/config.py`. Override any of it with a `CSRS_`-prefixed
environment variable or a `.env` file.

| Setting | Value | Note |
|---|---|---|
| Embedding model | `nomic-embed-text` | Mandated by the spec. 274 MB, 768 dimensions |
| Embedding batch size | 32 | |
| Default LLM | `llama3.2` | 2.0 GB. Most reliable of the five at staying grounded |
| Other LLMs | `qwen2.5:1.5b` (986 MB), `gemma2:2b` (1.6 GB), `phi4-mini` (2.5 GB), `gemma4:e2b` (7.2 GB) | All selectable from the dropdown |
| Chunk size | 400 tokens | Approximated as 4 characters per token, so chunking does not depend on a model tokenizer |
| Chunk overlap | 60 tokens | Real overlapping text, not padding |
| Context window | 8192 tokens | |
| Temperature | 0.1 | Low, because the job is reporting what a standard says, not writing prose |
| Model keep-alive | 30 minutes | Ollama's default is 5 min; the longer hold avoids a reload on every question |
| Chunks sent to the model | 5 | `rerank_top_n`. This is the generation budget, not the retrieval pool |
| Retrieval candidate pool | 20 dense + 20 BM25 | `top_k_dense` / `top_k_bm25`. At k=20 *sent to the model*, prompts filled 92.4% of `num_ctx` and Ollama truncated silently rather than erroring — which is why these are two settings and not one |
| Retrieval mode | `hybrid` | Dense + BM25 fused by RRF. `CSRS_RETRIEVAL_MODE=dense` reverts to semantic-only |
| RRF constant | 60 | `k=20` and `k=60` were both measured; the difference was 0.001 Recall@5 |
| Reranking | off | Built and measured, deliberately disabled. Section 8 explains why |
| Vector store | Chroma, persistent, cosine | `chroma_db/`, about 35 MB |
| PDF parser | Docling | `CSRS_PDF_PARSER=pypdf` selects the fast fallback |

---

## 7. Documents used

| Document | Format | Pages | Chunks | Ships in repo? |
|---|---|---:|---:|---|
| NIST SP 800-53 Rev. 5 | PDF | 492 | 2119 | No — fetched by `scripts/fetch_docs.py` |
| NIST CSF 2.0 | PDF | 32 | 209 | **Yes** — `docs/samples/`, public domain |
| OWASP Top 10 2021 | TXT | — | 147 | **Yes** — `docs/samples/`, CC BY 4.0 |
| NIST SP 1299 | PDF | 8 | 31 | No — fetched by script |

One PDF and one TXT are committed so a fresh clone is queryable immediately and both parsing
paths are exercised without any download.

**Two standards named in the specification are deliberately absent.** ISO/IEC 27001 is
copyrighted and sold by ISO; CIS Controls v8.1 requires registration and restricts
redistribution. Neither can be committed to a public repository.

This has a visible consequence, and it is the right one: asking *"What does ISO 27001 require
for access control?"* returns a refusal. The system declines rather than answering from the
NIST documents it does have. Drop a licensed copy into `docs/`, press reload, and the same
question answers normally.

---

## 8. What I would point out as the interesting parts

**A layout model instead of regex, and the failure that forced it.** The first PDF parser
used `pypdf` plus hand-written rules to strip page headers and footers. It took four rounds of
increasingly specific rules, and each round was only discovered by testing against a document
the previous round had never seen. Every rule was correct — but four rounds of corpus-tuned
rules is the signal that the approach will not generalise, and "works on documents nobody has
looked at yet" is exactly what the specification asks for. So the tool changed. Docling runs
a document-layout model that classifies page furniture structurally, suppressing it by
construction rather than by rule.

**Control IDs are first-class metadata.** In a standards document the identifier *is* the
semantics — losing `AC-2` from a chunk loses the ability to answer "what does AC-2 require".
The chunker extracts `AC-2`, `AC-2(1)` and CSF-style `GV.OC-01` identifiers and stores them
alongside the text. Nested enhancement headings that appear as a bare `(1)` are resolved
against the nearest enclosing control.

**Breadcrumbs help the vector without polluting the citation.** A chunk is embedded as
`section breadcrumb + text`, but stored and displayed as text alone. The vector gets the
context; the citation shows the real passage.

**Reloading is nearly free.** Files are fingerprinted by a SHA-256 of their bytes, checked
*before* the parser runs. A cold build is 316 s; an unchanged reload is 0.057 s with zero
embedding calls. Bytes are hashed rather than modification time, so a `git checkout` — which
rewrites timestamps constantly — does not trigger a five-minute rebuild.

**One facade, and neither UI crosses it.** No interface imports Chroma, Ollama or the
manifest. That single rule is what made a second interface possible without touching a line
of retrieval or generation code.

**The answer streams, and so does the progress.** The web UI shows tokens as they are
generated and live retrieval stages over an NDJSON stream. Both endpoints were verified to
return byte-identical answers at temperature 0.

**Citations carry real provenance.** Every answer shows which passages were retrieved, with
document, page, section breadcrumb, control ID, and cosine score — expandable to the full
retrieved text.

**The test suite proves the offline claim.** The 205 offline tests run with Ollama pointed at
a dead port. If any module silently reached the network, they would fail. That is a stronger
guarantee than reading the code and concluding nothing does.

**Retrieval is measured, not asserted.** 48 hand-authored question/answer pairs across five
categories — exact control lookup, semantic paraphrase, cross-document, out-of-scope (must
refuse), and all five of the specification's own example questions. `eval/run_eval.py` turns
them into Recall@k, MRR and nDCG@10 and writes a timestamped JSON per run. The metric
functions are unit-tested against hand-computed cases, because a buggy nDCG will happily
report improvement that isn't there.

---

## 9. What measuring changed

The through-line of this project is that measurement repeatedly disagreed with reasonable
assumptions. Each row cost real time, and each one is why some part of the system looks the
way it does.

| Assumption | What measuring showed |
|---|---|
| Collapsing the chunker's heading layer is a deletion | SP 800-53 emits 1075 headings, **all flat `##`** — it needed a rewrite, not a deletion |
| Migrating parsers is metadata-neutral | `control_id` coverage silently collapsed **92.1% → 0.0%**. No exception, no failing test |
| The stack is slow (19 s per answer) | It was fast at k=5. The default conflated *candidate pool* with *generation budget* |
| Docling costs ~6 min (its own benchmark) | **1.99 pages/s** — 1.5× faster than the vendor's M3 Max figure |
| Guard tests pass in-process | `chromadb` caches clients per path, giving **false passes**. Guards must run in separate processes |
| Hybrid retrieval will improve Recall@10 | Recall@10 **fell**. The metric was the wrong instrument (below) |
| A cross-encoder rerank costs ~30 ms | **1626 ms** for 40 candidates — 54× the budget |

**The parser decision is the one the project turns on.** The original `pypdf` parser needed
**four separate rounds** of increasingly specific rules to strip page furniture, and each
round was only discovered by testing against a document the previous round had never seen.
Every rule was correct. That is what makes it worth naming: four rounds of corpus-tuned
rules, each fixing a real defect found only on unseen input, is not a debugging streak — it
is the signal that the approach doesn't generalise. Docling's layout model classifies
`Page-header` and `Page-footer` structurally: **1937 items** suppressed on SP 800-53 with no
rule written for either of the two strings that took four rounds to kill.

**The silent regression is the measurement I would most want a reader to notice.** When the
parser changed, Docling began emitting control headings as real Markdown, so the ATX pattern
matched *first* and returned `control_id=None`. Nothing failed. No test went red, and the
breadcrumbs still looked right by eye. Exact-ID retrieval had simply lost its metadata. A
test suite structurally cannot catch that, which is why the acceptance criterion for that
step was a *measured coverage number on the real corpus* rather than a green suite.

### The Phase 3 metric was mis-specified, and finding that out was the result

Hybrid retrieval and reranking were both graded on Recall@10 and nDCG@10. Both "failed":

| configuration | rank-1 | Recall@5 | Recall@10 | MRR | nDCG@10 |
|---|---|---|---|---|---|
| dense only | 27/37 | 0.454 | **0.573** | 0.834 | **0.628** |
| **hybrid (dense + BM25, RRF)** | **29/37** | **0.461** | 0.565 | 0.855 | 0.625 |
| hybrid + rerank, MiniLM-L-12 | 33/37 | 0.439 | 0.525 | 0.920 | 0.624 |
| hybrid + rerank, TinyBERT-L-2 | 26/37 | 0.411 | 0.501 | 0.785 | 0.561 |

The metric was at fault, not the retrieval. The golden set's matchers resolve a control to
**all** of its chunks — 5 to 20 relevant chunks per question — so Recall@10 and nDCG@10
reward retrieving the whole control family. But generation only ever sees 5 chunks. Those
metrics were scoring something no user of this system experiences, and optimising toward
them would have meant optimising for breadth the model never reads.

Re-baselined on **rank-1 hit rate and Recall@5** — what actually reaches the model — hybrid
wins on both, and its real prize is `exact_id` MRR going **0.896 → 1.000**: exact control-ID
lookup becomes perfect. That is precisely what BM25 was added for, and it costs no
measurable latency. Hybrid is the default.

**Reranking was built, measured twice, and left off.** The large cross-encoder is the best
ranker in the table by a distance — 33/37 at rank 1, with `exact_id` and `cross_document`
MRR both 1.000 — and it costs 1.6 s per query against a ~30 ms budget. The small one is
fast enough and ranks *worse than not reranking at all*. flashrank has no intermediate
English cross-encoder, so there is no third option to try. `rerank_enabled` ships `False`,
the code stays, and both models are recorded above rather than quietly dropped.

**One finding invalidated a planned feature.** The intended defence against confabulation
was a retrieval-score confidence gate, calibrated on a 0.654–0.684 band. The system's worst
surviving answer scores **0.7127** — above that band, and well above the 0.5685 that would
have caught an earlier hallucination. A single scalar threshold provably cannot separate
*confidently-wrong-but-well-retrieved* from *nothing-relevant-retrieved*. They are different
failure classes and need more than one number.

### Page citations were verified with a different library

Page numbers are the most load-bearing metadata here: an off-by-one would corrupt every
citation and look completely fine. Trusting Docling to check Docling proves nothing, so
cited pages were re-read with **`pypdf`** — PDF pages 46 and 47 both contain `AC-2`, page 47
carries the automated-mechanisms enhancement, SP 1299 page 2 has all six CSF function names.
No off-by-one. That check also settled a choice: citations use the **1-based PDF page
position**, not the printed page number. SP 800-53's PDF page 46 prints "PAGE 19" — but the
printed number is stripped as furniture and doesn't survive parsing, so citing it would mean
citing a number the system can no longer verify.

---

## 10. What isn't built yet

Stated plainly, because these are the questions worth asking.

**No conversational memory.** This is the bonus item in section 4 of the specification, and
not having it has one reproducible cost. Asked cold, *"Explain the Identify function."*
retrieves SP 800-53's `SI-19 DE-IDENTIFICATION` and answers confidently about the wrong
thing. Ask *"Explain the Identify function of the NIST Cybersecurity Framework"* and it is
correct. Bare "Identify" collides lexically with de-identification, and SP 800-53 is 2119 of
the corpus's 2506 chunks, so it dominates the candidate pool. In the specification, that
question directly follows "What are the functions of the NIST Cybersecurity Framework?" — it
is a *follow-up*, and conversational context is exactly what resolves it. The failure appears
precisely where the specification predicted it would.

**No retrieval configuration fixes that question, and I checked.** Dense puts the right
chunk at rank 6; hybrid at 12; hybrid plus reranking back at 6; dense plus reranking loses
it from the top 20 entirely. It is not a retrieval-tuning problem, which is the clearest
evidence that conversational rewriting — not more retrieval work — is what it needs.

**Parent–child retrieval is not built.** Chunks are retrieved and passed to the model as-is;
there is no expansion to a surrounding parent section for context. Answers are grounded in
the exact retrieved passage, which is honest but sometimes narrower than a reader would want.

**Reranking ships disabled.** Built, measured against both available cross-encoders, and left
off — the numbers are in section 9.

**Refusal detection is exact-match.** A model that refuses in its own words instead of the
configured sentence is recorded as having answered. This under-reports refusals; it never
causes a wrong answer.

**Citations are structural, not inline.** The UI shows every retrieved chunk in full, but
does not mark which sentence came from which source — the model emits no citation markers, so
per-claim attribution would mean guessing.

**Smaller models are less reliable.** All five required LLMs work, but they are not equally
good at staying grounded. `qwen2.5:1.5b` has been measured refusing a question squarely in the
corpus that `llama3.2` and `gemma2:2b` both answered from identical retrieved chunks. That is
why `llama3.2` is the default.

[ROADMAP.md](ROADMAP.md) has the task breakdown, including the cards these come from.

---

## 11. Running it

```bash
uv sync                                              # dependencies
ollama serve &                                       # local model server
uv run python scripts/warm_models.py --pull-ollama   # all six models
python scripts/fetch_docs.py                         # corpus
uv run streamlit run src/csrs/app.py                 # http://localhost:8501
```

For the web UI instead: `(cd frontend && npm install && npm run build)` then
`uv run csrs-api` on http://127.0.0.1:8000.

The first launch takes about five minutes while the index is built. Every launch after that
is under a second. Full installation detail, troubleshooting and the document-adding workflow
are in [README.md](README.md).
