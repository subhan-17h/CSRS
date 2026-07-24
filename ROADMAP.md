# ROADMAP.md — Building CSRS

**Cybersecurity Standards RAG System** · plan written 2026-07-21

A teaching roadmap. Every task states *why it exists* and *what concept it teaches*, because the goal is to understand RAG, not just to produce a working app. Evidence for each choice lives in [RESEARCH.md](RESEARCH.md); reference implementations in [OS_REPOS.md](OS_REPOS.md).

---

## How to use this

**Task cards** look like this:

> **Goal** — one sentence · **Why** — the concept it serves · **Learn** — the transferable idea
> **Files** · **Steps** · **Done when** — observable, checkable · **Gotchas** · **Reading**

**Rules of engagement:**
1. **One task at a time.** Each is sized for a single sitting.
2. **"Done when" is not optional.** If you can't demonstrate it, it isn't done. ([CLAUDE.md](CLAUDE.md): *never mark a task complete without proving it works*.)
3. **Every phase ends runnable.** No phase leaves the app broken overnight.
4. **Phase 3 measures before it optimises.** Build the eval harness first, then change retrieval. Otherwise you're guessing.

**Phase map:**

| Phase | Outcome | Feels like |
|---|---|---|
| 0 | Environment + models + corpus | Setup |
| 1 | **A question gets a grounded answer** | The lightbulb |
| 2 | Every spec requirement met | Submittable |
| 3 | Retrieval measurably better | Engineering |
| 4 | Answers cited, refusals correct, chat works | Polish |
| 5 | Faster + optional upgrades | Optimisation |
| 6 | README, packaging, offline proof | Shipping |

**Phase 1 is the important one.** By its end the entire RAG loop is real. Everything after improves a system that already works — which is the right shape for a project like this, and the reason the walking skeleton comes before the good chunker.

---

## Architecture

```
CSRS/
├─ docs/                        ← standards PDFs/TXTs (watched, gitignored except samples)
├─ src/csrs/
│  ├─ config.py                 pydantic-settings; all tunables in one place
│  ├─ models.py                 Chunk, Document, RetrievedChunk, Answer
│  ├─ loaders/
│  │   ├─ base.py               DocumentParser protocol
│  │   ├─ text.py               TXT
│  │   ├─ pdf.py                pypdf + pdfplumber          (fallback)
│  │   └─ docling_parser.py     Docling + TableFormer       (default)
│  ├─ chunking.py               control-aware recursive splitter + breadcrumbs
│  ├─ embeddings.py             Ollama embed — OWNS the search_document:/search_query: prefixes
│  ├─ store.py                  Chroma + bm25s, content-hash incremental indexing
│  ├─ retrieval.py              dense ∥ BM25 → RRF → FlashRank → parent expansion
│  ├─ generation.py             prompt assembly, streaming, citation parsing, refusal
│  ├─ pipeline.py               the one facade the UI talks to
│  └─ app.py                    Streamlit
├─ eval/                        golden_set.yaml + metrics harness
├─ scripts/                     fetch_docs.py · warm_models.py · ingest.py
├─ tests/
└─ tasks/todo.md · lessons.md
```

**The load-bearing boundary is `pipeline.py`.** The UI never touches Chroma, Ollama, or FlashRank directly. That single rule is what makes the codebase modular in a way a reviewer can see at a glance — and it means the eval harness can drive the same pipeline the UI does, with no duplication.

---

# Phase 0 — Ground truth

*Nothing works until the environment does. Deliberately boring.*

### T-0.1 · Project skeleton with uv
**Goal** Reproducible Python 3.12 project.
**Why** A grader's first five minutes decide their impression.
**Learn** Lockfile-based reproducibility; why `uv.lock` beats a loose `requirements.txt`.
**Files** `pyproject.toml`, `.gitignore`, `src/csrs/__init__.py`
**Steps**
1. `git init` (not currently a repo).
2. `uv init --python 3.12`; src-layout package `csrs`.
3. Dependency groups: core (including Docling) / `dev` / `eval`.
4. Add `ruff`; configure line-length 100, `select = ["E","F","I","UP","B"]`.
5. `.gitignore`: `.venv`, `__pycache__`, `chroma_db/`, `docs/*.pdf`, `!docs/samples/`.
**Done when** `uv sync` succeeds and `uv run ruff check .` is clean.
**Gotchas** Local Python is 3.10 — `uv python pin 3.12` fetches 3.12 rather than failing. Don't list `uv` as a project dependency; it's a tool.

### T-0.2 · Ollama + all mandated models
**Goal** Every model the spec requires, pulled locally.
**Why** Non-negotiable spec requirement, and everything downstream depends on it.
**Learn** How local model serving works; quantisation tags.
**Steps**
1. Install Ollama; confirm `ollama serve` is reachable at `127.0.0.1:11434`.
2. `ollama pull nomic-embed-text` — **mandatory embedder**.
3. Pull each LLM: `llama3.2`, `qwen2.5:1.5b`, `gemma2:2b`, `phi4-mini`.
4. For the spec's `gemma4:e2b`: verify it exists in the registry. If it doesn't, substitute `gemma3:4b` **and record the substitution in the README** — do not silently drop a listed model.
5. Note disk usage; sanity-check `ollama run qwen2.5:1.5b "hello"`.
**Done when** `ollama list` shows the embedder plus ≥4 LLMs, and a manual prompt returns text.
**Gotchas** Default tags are already Q4_K_M — no manual quantisation needed. First pull is several GB; not offline-capable, which is precisely why the README documents it as a setup step.

### T-0.3 · Corpus fetch script
**Goal** `scripts/fetch_docs.py` downloads the redistributable standards.
**Why** The grader needs documents, and we cannot legally commit all of them.
**Learn** Licensing as an engineering constraint, not an afterthought.
**Files** `scripts/fetch_docs.py`, `docs/samples/`, `docs/README.md`
**Steps**
1. Download NIST CSF 2.0, SP 800-53 Rev 5, SP 1299, OWASP Top 10 → `docs/`.
2. Commit one small public-domain sample so a fresh clone runs immediately.
3. `docs/README.md`: per-document source + licence, CIS registration note, and the ISO 27001 exclusion stated plainly.
**Done when** A fresh clone + `python scripts/fetch_docs.py` yields a populated `docs/`.
**Gotchas** Never commit CIS or ISO material. Check bytes downloaded — NIST occasionally serves an HTML error page with a `.pdf` URL.
**Reading** → [OS_REPOS.md §8](OS_REPOS.md#8-corpus-sources-and-licensing)

### T-0.4 · Config module
**Goal** One typed home for every tunable.
**Why** You'll be adjusting chunk size, `top_k`, and thresholds constantly in Phase 3. Hunting magic numbers across files wastes hours.
**Learn** Centralised typed configuration.
**Files** `src/csrs/config.py`, `.env.example`
**Steps** `pydantic-settings` `Settings` with: `ollama_host`, `embed_model`, `default_llm`, `docs_dir`, `chroma_dir`, `chunk_size=400`, `chunk_overlap=60`, `top_k_dense=20`, `top_k_bm25=20`, `rrf_k=60`, `rerank_top_n=5`, `refusal_threshold`, `num_ctx=8192`, `keep_alive="30m"`.
**Done when** `from csrs.config import settings; print(settings)` works and `.env` overrides apply.

---

# Phase 1 — Walking skeleton

*The whole loop, end to end, at its simplest. TXT only, no PDFs, no hybrid, no reranking. Do not skip ahead — a working simple system beats a half-built sophisticated one, and everything in Phases 3–5 is measured against this baseline.*

### T-1.1 · Data models
**Goal** `Chunk`, `Document`, `RetrievedChunk`, `Answer`.
**Why** These types are the contract between every module.
**Learn** Designing around the data that flows, not the functions that act.
**Files** `src/csrs/models.py`
**Steps** Pydantic models. `Chunk` carries: `id`, `text`, `doc_name`, `section`, `page`, `control_id`, `parent_id`, `content_hash`.
**Done when** Models instantiate and validate.
**Gotchas** Include `page` and `control_id` **now**, even though nothing populates them until Phase 2. Retrofitting fields through a storage layer is far more painful than carrying `None` for a week.

### T-1.2 · TXT loader
**Goal** Read every `.txt` in `docs/` into `Document`s.
**Files** `src/csrs/loaders/base.py`, `loaders/text.py`
**Steps** Define a `DocumentParser` `Protocol` (`.parse(path) -> Document`), then implement TXT against it.
**Done when** Loading a sample TXT returns a `Document` with correct text.
**Gotchas** The protocol exists from day one so PDF and Docling slot in without touching callers. This is the interface the spec's "extensible" requirement actually cashes out to.

### T-1.3 · Naive chunker
**Goal** Split text into ~400-token chunks with ~60 overlap.
**Why** Embeddings represent a *fixed-size* semantic unit; whole documents are too coarse to retrieve usefully.
**Learn** Chunking as the precision/context trade-off — the single most consequential knob in RAG.
**Files** `src/csrs/chunking.py`
**Steps** Recursive separator cascade `["\n\n", "\n", ". ", " "]`; approximate tokens as `chars / 4`; apply overlap; emit `Chunk`s.
**Done when** A 10k-char document yields ~8–10 chunks, each under the limit, with visible overlap.
**Gotchas** Overlap exists so a sentence spanning a boundary survives in at least one chunk. Verify it's real by printing consecutive chunk tails and heads.
**Reading** → [RESEARCH.md §1](RESEARCH.md#1-chunking)

### T-1.4 · Embeddings — ⚠ the highest-risk task in the project
**Goal** Embed text via Ollama with **correct task prefixes**.
**Why** `nomic-embed-text` *requires* `search_document:` on indexed text and `search_query:` on queries. Omitting them raises no error and returns plausible vectors — retrieval just gets quietly, permanently worse.
**Learn** Silent-failure modes, and why you encapsulate a rule instead of documenting it.
**Files** `src/csrs/embeddings.py`, `tests/test_embeddings.py`
**Steps**
1. `embed_documents(texts) -> list[list[float]]` — prepends `search_document: ` to each.
2. `embed_query(text) -> list[float]` — prepends `search_query: `.
3. Batch documents (~32) via `ollama.embed`.
4. **No other module may call `ollama.embed` directly.**
5. Unit-test that both functions prepend correctly (monkeypatch the client; no Ollama needed).
**Done when** Both functions return 768-dim vectors, and the prefix tests pass.
**Gotchas** The asymmetry *is* the mechanism — same prefix for both is the subtle version of the same bug. Assert `len(vec) == 768` once; a wrong length means the wrong model is loaded.
**Reading** → [RESEARCH.md §8](RESEARCH.md#8-nomic-embed-text-the-details-that-actually-matter)

### T-1.5 · Chroma store
**Goal** Persist chunks + embeddings; query by similarity.
**Learn** How a vector index actually stores and searches.
**Files** `src/csrs/store.py`
**Steps**
1. `PersistentClient(path=settings.chroma_dir)`.
2. Create collection with **`metadata={"hnsw:space": "cosine"}`**.
3. `add_chunks()` passing **our own** embeddings.
4. `search(query_embedding, k)` → `RetrievedChunk`s with distances.
**Done when** Add 10 chunks, query a related phrase, and the sensible chunk ranks first.
**Gotchas** **Two silent traps.** (a) Chroma defaults to L2; our vectors are normalised and want cosine. (b) If you don't pass embeddings, Chroma downloads its own ONNX model — breaking offline operation *and* silently bypassing the mandated embedder. Always pass vectors.
**Reading** → [OS_REPOS.md §5](OS_REPOS.md#5-local-vector-stores)

### T-1.6 · Generation with grounding
**Goal** Answer from retrieved context, refusing when it's absent.
**Why** "Avoid generating information not present in the documents" is the core spec requirement — and the hard part with a 1.5B model.
**Learn** Prompt structure for small models; why instruction placement matters.
**Files** `src/csrs/generation.py`
**Steps**
1. Assemble: context chunks labelled `[S1]…[Sn]`, then question, then instruction.
2. Instruction **after** context — closer to the generation point.
3. Give a literal refusal string to emit, not an abstract "say you don't know".
4. Call `ollama.chat` with `num_ctx` and `keep_alive` from config.
**Done when** An in-context question answers correctly; an out-of-context question returns the refusal string.
**Gotchas** Keep the system prompt short — long instruction lists *reduce* compliance at this model size. Test refusal explicitly with something absurd ("What is the capital of France?"); models love to be helpful.
**Reading** → [RESEARCH.md §5](RESEARCH.md#5-grounding-refusal-and-citation)

### T-1.7 · Pipeline facade
**Goal** `Pipeline.index()` and `Pipeline.ask(question)`.
**Why** One seam between UI and internals.
**Files** `src/csrs/pipeline.py`
**Done when** A script can index `docs/` and answer a question in two calls.

### T-1.8 · 🎉 Minimal Streamlit app
**Goal** Question box → answer on screen.
**Why** Proof the loop is real.
**Files** `src/csrs/app.py`
**Steps** `st.text_input` + `st.write`; `@st.cache_resource` for the pipeline; index on first run.
**Done when** `uv run streamlit run src/csrs/app.py` answers a question about a TXT in `docs/`.
**Gotchas** Streamlit re-runs the whole script per interaction — without `@st.cache_resource` you re-index on every keystroke. Understanding this now prevents a class of confusion later.

> **Checkpoint.** You have a complete RAG system. Ask it several questions. Note what it gets wrong — those failures are what Phases 3 and 4 exist to fix, and having seen them makes the rest of this roadmap concrete rather than abstract.

---

# Phase 2 — Spec completion

*Every literal requirement in `CSRS.md`, demoable.*

### T-2.1 · PDF parsing
**Goal** Extract text + **page numbers** from PDFs.
**Why** The corpus is PDFs, and page numbers are what make Phase 4's citations verifiable.
**Learn** Why PDF extraction is genuinely hard: PDFs describe glyph positions, not text.
**Files** `src/csrs/loaders/pdf.py`
**Steps**
1. `pypdf` for per-page text; retain page index on every extracted block.
2. `pdfplumber` for pages where tables are detected; render tables as pipe-delimited text.
3. Normalise whitespace; drop repeated headers/footers.
4. Register in the loader registry by extension.
**Done when** NIST CSF 2.0 parses with correct page numbers and control tables that are still readable as tables.
**Gotchas** Ligatures (`ﬁ`) and soft hyphens corrupt keyword matching — normalise. Expect to iterate here; **spot-check the output text**, don't assume.
**Reading** → [OS_REPOS.md §3](OS_REPOS.md#3-pdf-parsing)

### T-2.2 · Structure-aware chunking + breadcrumbs
**Goal** Split on control boundaries; prepend a hierarchy breadcrumb.
**Why** Standards are rigidly hierarchical, and a chunk that says which control it is retrieves far better than one that doesn't.
**Learn** Contextual retrieval — the free, deterministic form.
**Files** `src/csrs/chunking.py`
**Steps**
1. Regex control IDs: `AC-2`, `AC-2(1)`, `ID.AM-01`, `CC 1.1`, section numbers.
2. Prefer splitting **at** control boundaries over mid-control.
3. Track the heading stack while walking the document.
4. Prepend `NIST SP 800-53 Rev5 › AC Access Control › AC-2 Account Management` to chunk text **before embedding**.
5. Populate `section`, `page`, `control_id` metadata.
**Done when** Chunks from SP 800-53 mostly correspond to single controls, and each begins with its breadcrumb.
**Gotchas** The breadcrumb goes into the **embedded** text, not just metadata — that's what makes it affect retrieval. Keep the raw text separately for display, so citations show the control, not the breadcrumb.
**Reading** → [RESEARCH.md §1](RESEARCH.md#contextual-chunk-headers-contextual-retrieval)

### T-2.3 · Content-hash incremental indexing
**Goal** Re-embed only new or changed files.
**Why** The spec's "Restart & Reload" button is unusable if it re-embeds 400 pages every press.
**Learn** Content-addressed caching — a pattern that recurs everywhere.
**Files** `src/csrs/store.py`
**Steps**
1. SHA-256 each file; persist a manifest `{path: hash}`.
2. On index: unchanged → skip; changed → delete chunks by `doc_name`, re-add; removed → delete.
3. Report added/updated/skipped/removed counts.
**Done when** Second index run of an unchanged corpus completes in <1 s and reports all-skipped; touching one file reprocesses only that file.
**Gotchas** Hash **content**, not mtime — git checkouts change mtimes constantly.

### T-2.4 · Model dropdown from Ollama
**Goal** Populate the selector from actually-installed models.
**Why** Spec requirement, and a hardcoded list that lies is worse than no list.
**Files** `src/csrs/app.py`
**Steps** `ollama.list()` → filter to the spec's supported LLMs → intersect with installed → sidebar `st.selectbox`. Show a clear warning when a required model is missing.
**Done when** The dropdown reflects reality, and switching models changes which model answers.
**Gotchas** Handle Ollama being down with a friendly message, not a stack trace — this is the single most likely failure a grader will hit.

### T-2.5 · Restart & Reload + document list
**Goal** The spec's button, plus the loaded-document display.
**Why** Both explicit requirements. The button is also where cache bugs live.
**Learn** Streamlit's caching model and how to invalidate it correctly.
**Files** `src/csrs/app.py`
**Steps**
1. Sidebar list: filename, chunk count, page count.
2. "Restart & Reload Documents" → clear manifest → `st.cache_resource.clear()` → rebuild → `st.rerun()`.
3. `st.status` for progress during ingestion.
**Done when** Dropping a new PDF into `docs/` and pressing the button makes it queryable — with no code change and no app restart.
**Gotchas** Order matters: clear caches *before* rebuilding, or the stale pipeline object is reused. Test the actual spec scenario — add a file at runtime, press the button.

### T-2.6 · Sidebar settings
**Goal** Surface the tunables.
**Steps** Model selector, `top_k`, temperature, a "documents loaded" summary, and an Ollama connection indicator.
**Done when** The sidebar matches the spec's list of required UI elements.

> **Checkpoint.** Walk `CSRS.md` §1–6 line by line against the app. Every requirement should be demonstrable. **This is a submittable state** — everything after is quality.

---

# Phase 3 — Retrieval quality

*Measure first, then change. In that order — otherwise every improvement below is a guess.*

> **The success metric was re-baselined after T-3.5, and the cards below say so.** As
> originally written, T-3.4 and T-3.5 were graded on Recall@10 and nDCG@10. Both are the
> wrong instrument for this system: the golden set's matchers resolve a control to *all* of
> its chunks (5–20 relevant per pair), so those metrics reward retrieving the whole control
> family — while generation only ever sees `rerank_top_n` (5) chunks. They scored something
> no user experiences. **The primary metrics are now rank-1 hit rate and Recall@5**, with
> Recall@10 and nDCG@10 still reported as secondaries. The original criteria are kept below
> each card so the change is auditable rather than quietly rewritten.

### T-3.1 · Golden set
**Goal** 40–60 `question → expected source` pairs.
**Why** Without ground truth you cannot tell improvement from noise.
**Learn** Building evaluation data — the least glamorous, highest-leverage step in applied ML.
**Files** `eval/golden_set.yaml`
**Steps** Cover deliberately: exact-ID lookups (`What does AC-2 require?`), semantic paraphrase (`How do I manage user accounts?`), cross-document, **out-of-scope (must refuse)**, and the spec's own example questions.
**Done when** ≥40 pairs, each naming the document + control/section that answers it.
**Gotchas** Write these **by reading the documents**, not from memory. A wrong golden set is worse than none — it will send you optimising toward the wrong target.
**Reading** → [RESEARCH.md §7](RESEARCH.md#7-evaluation)

### T-3.2 · Metrics harness
**Goal** Recall@k, MRR, nDCG@10 over the golden set.
**Why** Turns "feels better" into a number.
**Learn** IR metrics — what each actually measures.
**Files** `eval/run_eval.py`, `tests/test_metrics.py`
**Steps** Run each question through retrieval; compare returned chunk metadata to expected sources; print a table; save a timestamped JSON. Unit-test the metric functions on hand-computed cases.
**Done when** `uv run python eval/run_eval.py` prints a baseline table. **Record these numbers** — every task below is measured against them.
**Gotchas** Test the metrics themselves. A buggy nDCG will happily report improvement that isn't there.

### T-3.3 · BM25 index
**Goal** Keyword retrieval alongside dense.
**Why** Embeddings are poor at alphanumeric IDs — a 768-dim vector doesn't reliably separate `AC-2` from `AC-3`. BM25 does this exactly.
**Learn** Lexical vs. semantic retrieval, and why each fails where the other succeeds.
**Files** `src/csrs/store.py`
**Steps** Build a `bm25s` index over the same chunks; persist beside Chroma; rebuild on reindex; expose `search_bm25(query, k)`.
**Done when** ✅ Querying `AC-2` returns an AC-2 chunk at rank 1 — `NIST.SP.800-53r5.pdf:207`. *Original criterion also required confirming dense alone does worse on that query; dense already returned an AC-2 chunk at rank 1, so the gap does not appear on a single query. It appears across the category: BM25 takes `exact_id` MRR from 0.896 to 1.000, which is the same claim measured properly.*
**Reading** → [RESEARCH.md §2](RESEARCH.md#bm25-sparse-retrieval)

### T-3.4 · RRF fusion
**Goal** Merge dense + BM25 by rank.
**Why** Highest-ROI change in the system.
**Learn** Why rank-based fusion beats score-based: cosine similarities and BM25 scores are on incomparable scales, and RRF sidesteps calibration entirely.
**Files** `src/csrs/retrieval.py`, `tests/test_rrf.py`
**Steps** `RRF(d) = Σ 1/(k + rank_i(d))`, `k=60`; dedupe by chunk id; unit-test with hand-built rankings.
**Done when** ✅ **Run the eval harness. Rank-1 hit rate and Recall@5 both improve over T-3.2's baseline** — 27/37 → 29/37 and 0.454 → 0.461, with `exact_id` MRR 0.896 → 1.000. Hybrid is now the default `retrieval_mode`. *Original criterion was "Recall@10 and MRR both improve": MRR improved (0.834 → 0.855), Recall@10 fell (0.573 → 0.565). See the re-baseline note above — the fall is fusion trading family breadth for rank-1 precision, which is the trade this system wants.*
**Gotchas** RRF uses ranks *only* — if you find yourself passing scores in, you've misunderstood it. Try `k=20` and `k=60` and let the harness decide.
**Reading** → [RESEARCH.md §2](RESEARCH.md#hybrid-via-reciprocal-rank-fusion)

### T-3.5 · FlashRank reranking
**Goal** Cross-encoder rerank of the fused top-40 → top-5.
**Why** A cross-encoder sees query and document *together*, modelling interactions a bi-encoder structurally cannot.
**Learn** Bi-encoder vs. cross-encoder; the retrieve-then-rerank pattern.
**Files** `src/csrs/retrieval.py`, `scripts/warm_models.py`
**Steps**
1. `Ranker(model_name="ms-marco-MiniLM-L-12-v2")`, cached at module level.
2. Rerank the fused candidates; keep top-5 **and their scores** (Phase 4's refusal gate needs them).
3. `scripts/warm_models.py` to pre-download the ONNX weights.
**Done when** ⚠️ **Built, measured, and deliberately not enabled.** `rerank_enabled` ships `False`. Both criteria failed on measurement, and both flashrank English cross-encoders were tested rather than one:

| model | rank-1 | MRR | nDCG@10 | latency, 40 candidates |
|---|---|---|---|---|
| none (hybrid) | 29/37 | 0.855 | 0.625 | — |
| `ms-marco-MiniLM-L-12-v2` | **33/37** | **0.920** | 0.624 | **1626 ms** (54× the ~30 ms budget) |
| `ms-marco-TinyBERT-L-2-v2` | 26/37 | 0.785 | 0.561 | 82 ms |

The large model buys real rank-1 precision (`exact_id` and `cross_document` MRR both 1.000) at 1.6 s per query; the small one is fast enough but ranks *worse than not reranking at all*. flashrank has no intermediate English cross-encoder, so there is no third option. nDCG@10 never improved under either. The capability stays behind the flag, selectable and measured.
**Gotchas** Rerank the **fused** list, not dense-only — reranking a bad candidate pool can't fix it. Document the one-time weight download in the README next to `ollama pull`.
**Reading** → [RESEARCH.md §3](RESEARCH.md#3-reranking)

### T-3.6 · Parent–child retrieval
**Goal** Retrieve precise children, answer with parent context.
**Why** Resolves precision-vs-context: small chunks retrieve better, large chunks answer better.
**Learn** Small-to-big retrieval, and how our corpus's existing hierarchy makes it nearly free.
**Files** `src/csrs/chunking.py`, `src/csrs/retrieval.py`
**Steps** Emit parent chunks at control-family/section level with stable ids; set `parent_id` on children; **index children only**; after reranking, expand to parents, dedupe, and cap total context tokens.
**Done when** Eval shows equal-or-better retrieval while answers demonstrably have richer context; context stays within `num_ctx`.
**Gotchas** Cap the expansion — two parents from a 400-page document can blow the context window. Dedupe: five children often share one parent.
**Reading** → [RESEARCH.md §1](RESEARCH.md#parentchild-small-to-big-retrieval)

> **Checkpoint.** Produce a table: baseline → +BM25 → +RRF → +rerank → +parent-child, with Recall@10 / MRR / nDCG@10 per row. **This table is one of the strongest artefacts in the submission** — it shows engineering rather than assembly.

---

# Phase 4 — Answer quality

### T-4.1 · Inline citations
**Goal** Answers cite `[S1]`; UI resolves to `document › section › p.N` with expandable source text.
**Why** Converts "trust the model" into "check the source" — the whole point of a compliance tool.
**Learn** Attribution design; making citing *easier* for the model than not citing.
**Files** `src/csrs/generation.py`, `src/csrs/app.py`
**Steps** Label context chunks `[S1]…[S5]`; instruct the model to cite after each claim; regex the labels out of the answer; render a "Sources" `st.expander` with document, section, page, and retrieved text; handle hallucinated labels (`[S9]` when only 5 exist) gracefully.
**Done when** A spec example question returns an answer whose citations resolve to the correct pages.
**Gotchas** Small models cite inconsistently. Labels must be short and visually distinctive; verbose citation formats get mangled.

### T-4.2 · Confidence-gated refusal
**Goal** Refuse when retrieval is weak.
**Why** Spec: "inform the user when sufficient information cannot be found." Prompting alone is unreliable at 1.5B.
**Learn** CRAG's core idea, reduced to the part that pays for itself — a structural guard beats a politely-worded instruction.
**Files** `src/csrs/generation.py`, `src/csrs/pipeline.py`
**Steps** If top reranker score < `refusal_threshold`, return the refusal without generating. **Calibrate the threshold using the golden set's out-of-scope questions.** Show the confidence in the UI.
**Done when** Out-of-scope questions refuse; in-scope ones don't. Report both rates.
**Gotchas** Calibrate against data, don't guess. Too high and it refuses valid questions — the worse failure, since it looks broken.
**Reading** → [RESEARCH.md §4](RESEARCH.md#crag-reduced-to-what-we-actually-need)

### T-4.3 · Conversational query rewriting
**Goal** Rewrite follow-ups into standalone queries.
**Why** "How about least privilege?" retrieves noise. Rewritten against history, it retrieves correctly. **This is what makes the spec's conversational bonus real** rather than cosmetic.
**Learn** Query understanding as a first-class pipeline stage.
**Files** `src/csrs/generation.py`, `src/csrs/pipeline.py`
**Steps** If history exists, one small LLM call: history + question → standalone question. Retrieve with the rewrite; generate with the original. Show the rewrite in a collapsed UI element.
**Done when** A three-turn conversation with pronoun-laden follow-ups retrieves correctly at every turn.
**Gotchas** Never rewrite turn 1 — it adds latency and can distort a perfectly good question. Cap history at N turns.
**Reading** → [RESEARCH.md §6](RESEARCH.md#6-conversational-rag)

### T-4.4 · Chat UI + streaming
**Goal** Proper chat interface with streamed tokens.
**Why** Time-to-first-token drops below 1 s. Total time is unchanged; perceived speed transforms.
**Learn** Perceived vs. actual latency.
**Files** `src/csrs/app.py`
**Steps** `st.chat_message` / `st.chat_input`; history in `st.session_state`; `st.write_stream` over `ollama.chat(stream=True)`; sources expander per answer; a "Clear conversation" control.
**Done when** Tokens appear progressively; history persists across turns; clearing resets cleanly.
**Gotchas** Parse citations *after* the stream completes — you can't regex a half-written answer.

---

# Phase 5 — Optimisation & optional upgrades

*Everything here is measured against Phase 3's harness. If it doesn't improve the numbers, don't keep it.*

### T-5.1 · Performance pass
**Steps** Confirm `keep_alive="30m"`; batch embeddings at 32; LRU-cache query embeddings; time each pipeline stage and log it.
**Done when** A stage-by-stage timing table exists and matches [RESEARCH.md §9](RESEARCH.md#9-local--cpu-optimisation)'s expectations (~70 ms retrieval, ~3–5 s generation).
**Gotchas** **Read the timing table before optimising.** Retrieval is ~1% of query time; optimising it further is wasted effort.

### T-5.2 · LLM contextual headers (opt-in, hash-cached)
**Goal** LLM-written context blurb per chunk, cached by content hash.
**Why** Anthropic reports meaningful retrieval-failure reduction. We test whether it beats our free breadcrumb.
**Learn** How to evaluate a technique honestly instead of adopting it on reputation.
**Steps** Behind `settings.use_llm_headers`; generate one line per chunk; cache keyed by chunk hash so reload doesn't regenerate; **run the eval harness with it on and off**.
**Done when** You have a measured comparison — and a decision either way, recorded.
**Gotchas** Without the hash cache this makes "Reload" unusable. If it doesn't beat the breadcrumb, **leave it off and write down that you tested it.** A negative result you measured is worth more than a feature you assumed.

### T-5.3 · Docling optional parser (superseded by T-2.7)
**Status** Absorbed by T-2.7, which was pulled forward into Phase 2 and made Docling the default PDF parser.
**Goal** Delivered by T-2.7 with `docling_parser.py`, offline model warm-up, pinned `artifacts_path`, and a selectable pypdf fallback.
**Done when** Superseded: T-2.7 deliberately reversed this card's requirement that the default path must never require Docling. Docling is now a core dependency and the default parser.
**Gotchas** Keep the pypdf/pdfplumber path as a supported fallback; do not describe it as removed.
**Reading** → [OS_REPOS.md §3](OS_REPOS.md#docling-done-safely)

---

# Phase 6 — Submission

### T-6.1 · README
**Files** `README.md`
**Steps** Cover the spec's required sections: installation, setup, **how to add new documents**, how to run. Plus: architecture overview, the Phase 3 metrics table, model-substitution notes from T-0.2, the ISO 27001 licensing position, and troubleshooting (Ollama not running, missing models, first-index duration).
**Done when** Someone who has never seen the project can go from clone to answered question by following it literally.
**Gotchas** Actually follow your own README on a clean machine. Assumed steps are invisible to the author and glaring to a grader.

### T-6.2 · Packaging
**Steps** `uv lock`; export a pinned `requirements.txt` (`uv export --no-hashes --format requirements-txt`); verify a plain `pip install -r requirements.txt` works in a fresh venv.
**Done when** Both `uv sync` and `pip install -r requirements.txt` produce a working install.
**Gotchas** Export without dev groups. `requirements.txt` now includes the core Docling dependency; document `scripts/warm_models.py` as the required weights setup step.

### T-6.3 · Offline verification
**Goal** Prove the central claim.
**Steps** Fresh venv → install → `ollama pull` all models → `python scripts/warm_models.py` → index the corpus → **disable networking** → run the app → ask several questions.
**Done when** It answers with the network off. Note it in the README.
**Gotchas** This is the requirement most likely to be tested and most likely to fail — usually via Chroma's default embedder or FlashRank's un-warmed weights. Test it properly.

### T-6.4 · Tests & lint
**Steps** Unit tests for the pure logic: prefix handling, RRF, chunk boundaries, content hashing, citation parsing, metrics. Integration tests behind `@pytest.mark.ollama`. `ruff check` clean.
**Done when** `uv run pytest -m "not ollama"` passes without Ollama running, and the full suite passes with it.
**Gotchas** Tests that need Ollama must be *skippable* — a grader may run pytest before starting Ollama.

### T-6.5 · Final spec audit
**Steps** Walk the traceability matrix below line by line against the running app. Confirm sample documents are committed.
**Done when** Every row is verified in the running application, not merely believed.

---

## Requirements traceability

| `CSRS.md` requirement | Task(s) |
|---|---|
| Accept PDF and TXT | T-1.2, T-2.1 |
| Auto-load from `docs/` | T-1.7, T-2.3 |
| Multiple documents | T-2.3 |
| Detect new documents, no code changes | T-2.3, T-2.5 |
| "Restart & Reload Documents" button | T-2.5 |
| Extensible to new standards | T-1.2 (parser protocol), T-2.5 |
| Ingestion: read → extract → split → embed → store | T-1.2 – T-1.5, T-2.1, T-2.2 |
| Embedding automatic on load/reload | T-1.7, T-2.3 |
| Embed query, retrieve by semantic similarity | T-1.4, T-1.5 |
| Supply only retrieved context | T-1.6 |
| Keyword search alone insufficient | T-3.3, T-3.4 (hybrid, not keyword-only) |
| Answer from retrieved context | T-1.6 |
| Don't generate ungrounded information | T-1.6, T-4.1, T-4.2 |
| Inform when info not found | T-4.2 |
| Conversational context *(bonus)* | T-4.3, T-4.4 |
| Streamlit UI | T-1.8 |
| Question input | T-1.8, T-4.4 |
| Generated answer | T-1.8, T-4.4 |
| Loaded document list | T-2.5 |
| Current model selection | T-2.4 |
| Reload button | T-2.5 |
| Sidebar settings | T-2.6 |
| Ollama only, no cloud APIs | T-0.2 — enforced stack-wide |
| `nomic-embed-text` always | T-1.4 |
| Required LLMs selectable | T-0.2, T-2.4 |
| Runs completely offline | T-6.3 |
| Modular and maintainable | Architecture; T-1.7 facade |
| README with install/setup/add-docs/run | T-6.1 |
| `requirements.txt` / `pyproject.toml` | T-0.1, T-6.2 |
| Sample documents | T-0.3 |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Missing `search_document:`/`search_query:` prefixes** | High | High — silent 20–50% quality loss | Encapsulated in `embeddings.py`; unit-tested (T-1.4) |
| **Chroma defaults to L2 not cosine** | High | Medium — silent degradation | Explicit `hnsw:space` at creation (T-1.5) |
| **Chroma's default embedder downloads a model** | Medium | High — breaks offline *and* bypasses mandated model | Always pass our own vectors (T-1.5); verified in T-6.3 |
| **Ollama not running on grader's machine** | High | High — app appears broken | Friendly connection check + README troubleshooting (T-2.4, T-6.1) |
| **FlashRank weights not warmed → offline failure** | Medium | High | `warm_models.py` + README step (T-3.5); verified T-6.3 |
| **First index is slow on SP 800-53** | High | **High** — looks hung for minutes | Measured after T-2.7: a full-corpus index is **336 s** with Docling (was ~52 s with pypdf). `st.status` progress and content-hash caching are now load-bearing, not cosmetic — and T-2.3 must hash **file bytes and skip before `parse()`**, or the cost is paid on every run anyway (T-2.3, T-2.5) |
| **Small models ignore grounding instructions** | High | High | Layered: prompt + confidence gate + citations (T-1.6, T-4.1, T-4.2) |
| **PDF table extraction mangles control tables** | High | Medium | Docling TableFormer by default; pypdf/pdfplumber fallback (T-2.7) |
| **`gemma4:e2b` may not exist in the registry** | Medium | Low | Verify at T-0.2; substitute and **document** |
| **Chroma HNSW corruption on hard exit** | Low | Medium | Reload button rebuilds; document `rm -rf chroma_db/` recovery |
| **Context overflow from parent expansion** | Medium | Medium | Cap expansion, dedupe parents, enforce token budget (T-3.6) |
| **Scope creep into Phase 5 before Phase 2 is done** | Medium | Medium | Phase 2 is submittable; treat it as the real deadline |

---

## Working conventions

Per [CLAUDE.md](CLAUDE.md):
- `tasks/todo.md` tracks the active phase with checkable items; mark them off as you go.
- `tasks/lessons.md` captures any correction, so the same mistake isn't repeated.
- Nothing is "done" without its **Done when** demonstrated.
- **Commit after every task, and again at the end of every phase** — one task per commit,
  subject line prefixed with the task id (`feat(T-1.4): ...`). Commit only after the
  "Done when" is demonstrated, so the history records verified work rather than intent.
  See [CLAUDE.md](CLAUDE.md#commit-discipline).
- Prefer the simple change. Most tasks here should touch one or two files.

**If you do only part of this roadmap:** Phases 0–2 give a complete, correct, submittable application. Phase 3 is what makes it good, and its metrics table is what makes that visible to someone else.
