# tasks/todo.md

Active work tracker. Full plan: [ROADMAP.md](../ROADMAP.md).

**Status:** Phases 0 and 1 complete and verified. T-2.1 is complete.

---

## Phase 0 — Ground truth

- [x] **T-0.1** Project skeleton with uv (`git init`, Python 3.12, `pyproject.toml`, ruff, dep groups)
- [x] **T-0.2** Install Ollama; pull `nomic-embed-text` + all required LLMs; verify `gemma4:e2b` exists or substitute + document
- [x] **T-0.3** `scripts/fetch_docs.py` + committed sample + `docs/README.md` licensing notes
- [x] **T-0.4** `config.py` with pydantic-settings; `.env.example`

## Phase 1 — Walking skeleton

- [x] **T-1.1** Data models (`Chunk`, `Document`, `RetrievedChunk`, `Answer`)
- [x] **T-1.2** `DocumentParser` protocol + TXT loader
  - Note: `iter_documents` uses `rglob`. Both samples live in `docs/samples/`, so a
    non-recursive scan finds zero documents. Do not "simplify" this to `glob`.
  - Note for T-2.1: adding the PDF parser is a one-line change to `_PARSERS` in
    `src/csrs/loaders/__init__.py`; no caller should need touching.
- [x] **T-1.3** Naive recursive chunker (~400 tok / ~60 overlap)
  - [x] Implement recursive separator splitting with a hard-cut fallback.
  - [x] Assemble bounded chunks with real text overlap and stable `Chunk` metadata.
  - [x] Cover size, overlap, sentence survival, determinism, and pathological inputs.
  - [x] Run lint, the full test suite, real-corpus evidence, and the ASCII proof.
- [x] **T-1.4** ⚠ Embeddings with `search_document:` / `search_query:` prefixes + unit tests
  - [x] Encapsulate distinct document/query prefixes behind exactly two public functions.
  - [x] Batch documents in configured groups while preserving input order.
  - [x] Reject every embedding whose width differs from the configured dimension.
  - [x] Unit-test prefixes, asymmetry, batching/order, and wrong-width failures offline.
  - [x] Run lint, offline tests, live Ollama comparison, API-call isolation, and ASCII proof.
- [x] **T-1.5** Chroma store with `hnsw:space=cosine`, own embeddings passed in
  - [x] Persist `Chunk` documents and metadata while omitting Chroma-invalid `None` values.
  - [x] Reconstruct equal `Chunk`s and convert cosine distance to `1.0 - distance` scores.
  - [x] Support caller-selected `k`, count, and delete-and-recreate reset behavior.
  - [x] Prove sensible first-place ranking, cosine configuration, round-trip, score order,
    reset, offline operation, lint, ASCII source, and no repository-local index leakage.
  - Ticked late by review: the Codex job died mid-verification (watcher caught it stale at
    180 s), so it never reached this step. Code was verified and committed as `16ee54a`.
- [x] **T-1.6** Grounded generation + literal refusal string
  - [x] Build a pure prompt assembler with `[S1]...` context, question, then instruction.
  - [x] Return an immediate refusal for empty context without calling Ollama.
  - [x] Call the configured Ollama client and classify only literal-refusal variants.
  - [x] Cover prompt order, complete context, call arguments, and refusal behavior offline.
  - [x] Prove lint, offline tests, live grounded/refusal behavior, ASCII, and repo hygiene.
  - Finding for **T-4.2**: prompt-only refusal is right at the margin. Across 7 probes
    llama3.2 never hallucinated, but on one out-of-scope question it refused *in its own
    words* ("I was unable to find any information about NIST CSF 2.0 functions") instead
    of emitting the literal string, so the exact-match `refused` flag read False. This is
    a detection false negative, not a grounding failure, and it is exactly why T-4.2 adds
    a structural confidence gate rather than trusting the prompt. Do NOT fix it by making
    `_is_refusal` fuzzy.
  - Calibration data for **T-4.2**, top retrieval score by question type:
    in-corpus 0.7402 / 0.7388 / 0.6841 · out-of-corpus 0.6535 / 0.5981 / 0.4922 / 0.4863.
    A `refusal_threshold` between 0.654 and 0.684 separates all seven, but the margin is
    ~0.03 -- calibrate against the full golden set (T-3.1), not these seven points.
- [x] **T-1.7** `Pipeline` facade (`index()`, `ask()`)
  - [x] Compose loading, chunking, embedding, storage, and generation behind one facade.
  - [x] Return indexing counts and expose document names and chunk count for UI callers.
  - [x] Cover repeatable full rebuilds, empty-store refusal, and caller-selected retrieval.
  - [x] Prove lint, offline tests on a dead Ollama port, live two-call use, boundary isolation,
    ASCII source, and repository hygiene.
  - ⚠ Finding for **T-3.5**: `ask()` sends all `top_k_dense` (20) chunks straight to
    generation, because Phase 1 has no reranker yet. Measured prompt size on the OWASP
    corpus: k=5 -> ~1900 tok (23% of `num_ctx`), k=10 -> ~3854 (47%), **k=20 -> ~7568
    (92.4%)**. It fits today, but a longer question or a denser corpus overflows, and
    Ollama truncates silently rather than erroring. `top_k_dense` is meant to be the
    *retrieval candidate pool*, not the generation context: once T-3.4/T-3.5 land, RRF and
    the reranker must narrow it to `rerank_top_n` (5) before generation. Until then, treat
    20 as the ceiling and do not raise it.
- [x] **T-1.8** 🎉 Minimal Streamlit app — **first end-to-end answer**
  - [x] Build a cached `Pipeline` and index once on the first Streamlit run.
  - [x] Show indexing progress, indexed document/chunk details, and one question/answer input.
  - [x] Render a focused Ollama connection remedy without hiding unrelated failures.
  - [x] Prove lint, offline tests, headless serving, a live answer, boundary isolation, ASCII,
    and repository hygiene.

## Phase 2 — Standards-aware ingestion

- [x] **T-2.1** PDF parsing with page numbers
  - [x] Add per-page text to the shared `Document` contract without changing TXT behavior.
  - [x] Parse PDF text and table rows while removing repeated running lines.
  - [x] Register PDF ingestion without changing callers.
  - [x] Cover pure helpers, registry lookup, and the committed CSF sample offline.
  - [x] Prove lint, offline tests, real-corpus behavior and timing, ASCII, and worktree hygiene.
  - ⚠ Finding for **T-2.3 / T-2.5**: registering `.pdf` changed what `iter_documents` sees.
    `docs/` now yields 3 PDFs + 1 TXT instead of 1 TXT, and `NIST.SP.800-53r5.pdf` alone
    takes **52.5 s to parse** (492 pages, 1.57 M characters) *before* a single embedding
    call. Phase 1's `Pipeline.index()` still does a full rebuild every run, so the first
    Streamlit launch now looks hung for a minute. That is exactly what T-2.3's content-hash
    incremental indexing and T-2.5's `st.status` progress exist to fix -- do not work around
    it by narrowing the corpus.
  - [x] **Follow-up fix** — the sample passed but the full corpus did not. Boilerplate
    survived on SP 800-53 for two reasons: NIST's block is *four* lines deep while detection
    looked at three (the DOI line was never even counted — 490/492 pages), and
    `CHAPTER THREE PAGE 19` changes every page so exact matching never counted it
    (465/492 pages). Fixed by widening the window to 5 and matching a digit-masked
    signature. A second pass caught chapter-scoped footers (`APPENDIX C PAGE #` and five
    others, 107 pages) that never reach a document-wide majority: a signature is also
    furniture when it sits in one fixed boundary slot on 3+ pages with a distinct number
    each time. Measured result **490 → 0** and **465 → 0**, with 728 control headings and
    2647 table rows intact.
    - ⚠ Do **not** "simplify" this to a plain low page threshold. Measured: a bare
      "3+ pages" rule also strips `Related Controls: AC-2.`, `[Withdrawn: Moved to SC-7(1).]`,
      `References: [SP 800-53].` and `[CNSSI 4009]`. The fixed-slot and distinct-number
      conditions are what separate a page stamp from real content.
  - Decision for **T-2.2**: cite the **1-based PDF page position**, not the printed page
    number. `reader.page_labels` returns plain sequential labels on all three PDFs, so it
    does not carry the printed number (index 45 of SP 800-53 prints "PAGE 19"), and the
    printed-number line is now stripped as furniture anyway.

---

## Review

*(Fill in after each phase: what changed, what was verified, what surprised you.)*

### Phase 0 — complete

**What was built:** `pyproject.toml` (uv, Python 3.12, ruff, 4 dep groups), `.gitignore`,
`src/csrs/config.py` + `.env.example`, `scripts/fetch_docs.py`, `docs/README.md`,
`docs/samples/NIST_CSF_2.0.txt`.

**Verified, not assumed:**

| Claim | Evidence |
|---|---|
| Reproducible env | `uv sync` OK on Python **3.12.13**; `uv.lock` present; `ruff check` clean |
| Config works | roadmap-mandated defaults match exactly; env-var, `.env`, and fail-fast validation each tested |
| All models present | `ollama list` shows embedder + **5/5** spec LLMs, 14 GB |
| Models actually generate | all 5 prompted; all returned text (qwen 0.8 s → gemma4 8.7 s) |
| Corpus fetches | 4 standards, ~10 MB; PDFs parse (CSF 32 p, SP 1299 8 p, SP 800-53r5 **492 p**) |
| Fetch is idempotent | second run reports all-skipped |
| Licensing enforced | `git check-ignore` confirms fetched corpus ignored, `docs/samples/` tracked |

**Findings that change later tasks:**

1. **`gemma4:e2b` exists.** Registry returns a valid 7.16 GB manifest; negative controls
   (`gemma4:e99b`, `gemma9`) 404, so the probe discriminates. **No substitution needed —
   close the risk-register row.** It is also the slowest model (8.7 s vs qwen's 0.8 s),
   which is why `default_llm` stays `qwen2.5:1.5b`.
2. **⚠ T-2.4 tag mismatch.** `ollama.list()` returns `llama3.2:latest` and
   `phi4-mini:latest`, but `CSRS.md` names them untagged. The dropdown's
   installed-vs-supported intersection **must normalise the `:latest` suffix** or it will
   wrongly report two mandated models as missing. A working `resolve()` was proven during
   T-0.2 verification.
3. **T-1.4/T-1.5 assumptions confirmed empirically**, not just from the model card:
   `nomic-embed-text` returns **768** dims with **L2 norm 1.0000** (so `hnsw:space=cosine`
   is correct), the task prefixes genuinely alter the vector (prefixed vs unprefixed
   doc cosine = 0.938), and prefixing *improves* doc↔query alignment (0.663 vs 0.595).
   Batching 32 inputs in one `embed()` call works.
4. **OWASP publishes no PDF** for 2021/2025 — markdown only. `fetch_docs.py` assembles the
   official English sources into an attributed TXT. Corrected in OS_REPOS.md §8.

**Surprises:** `fetch_docs.py` is stdlib-only by design and was verified running on the
**system Python 3.9.6**, so a grader can populate `docs/` before installing anything.
Every CSF 2.0 page repeats a running header — a preview of the T-2.1 header/footer
problem, already handled in the sample extraction.

**Deliberately not done:** no git commit (not requested); `ollama serve` is running as a
session process, not a `brew services` daemon.

### Phase 1 — complete

**T-1.3:** Added the recursive naive chunker and pure splitter. The synthetic 10k-character
fixture yields 8-10 bounded chunks, and tests prove literal 240-character overlap,
sentence-boundary survival, deterministic IDs and hashes, and hard-cut termination.
The real OWASP sample yielded 100 chunks (597-1600 characters, mean 1439.3), with exact
overlap visible across consecutive chunks. Full verification: ruff clean, 5 tests passed,
and both new Python files decode as ASCII.

**T-1.4:** Added the sole Ollama embedding boundary with separate, internal document and
query prefixes, configured 32-item batching, stable output order, and loud response count
and dimension validation. Offline tests exercise both prefix paths, explicit asymmetry,
70 inputs across 32/32/6 batches, order encoding, and 5-dimension failures. Full
verification: ruff clean, 11 non-Ollama tests passed, live document/query vectors were both
768 dimensions, prefixed versus unprefixed cosine changed (0.861095 versus 0.864256), no
other source module calls `.embed()`, and both new Python files decode as ASCII.

**T-1.6:** Added pure, directly tested prompt assembly with source-labelled chunks followed
by the question and a final compact grounding instruction containing the literal refusal.
Empty retrieval skips Ollama, while generated replies use narrow literal-refusal matching.
Ruff passed and all 24 non-Ollama tests passed against a dead port. The real OWASP corpus
answered "What is Broken Access Control?" with `refused=False`; the same top-5 retrieval
flow answered "What is the capital of France?" with the exact configured refusal and
`refused=True`. Both new Python files decode as ASCII, and the index lived in a temp dir.

**T-1.7:** Added the public `Pipeline` composition boundary with full-rebuild indexing,
structured document/chunk counts, document names, chunk count, retrieval defaults, and an
empty-store refusal that skips both embedding and generation. Four offline facade tests cover
the repeat-index regression and caller-selected `k`; the full dead-port suite passed 28 tests.
The live two-call proof indexed the real OWASP TXT into a temporary Chroma directory (1 document,
100 chunks, 4.65 s), answered Broken Access Control, and refused the France question exactly.
Ruff, byte-level ASCII decoding, dependency-boundary grep, diff checks, and worktree hygiene all
passed.

**T-1.8:** Added the minimal Streamlit walking skeleton: a cached first-run index behind the
`Pipeline` facade, visible indexing progress, indexed document/chunk details, one question input,
and the answer text. Connection failures during indexing or answering render the exact `ollama
serve` remedy while unrelated errors remain visible. Ruff and all 28 offline tests passed; the
headless app returned HTTP 200 and was stopped, the real OWASP TXT indexed into 100 chunks in a
temporary directory and answered the Broken Access Control question, and a dead-port Streamlit
run rendered the expected remedy. Boundary grep, byte-level ASCII decoding, and repository hygiene
also passed.

### Phase 2 — in progress

**T-2.1:** Added page-preserving PDF extraction with pypdf, targeted pdfplumber table rendering,
Unicode and whitespace normalization, and repeated running-line removal. The PDF parser is in the
existing extension registry, while TXT documents and chunk metadata retain their prior defaults.
Ruff and all 34 offline tests passed against a dead Ollama port. The CSF sample parsed as 32 pages,
kept its unique Appendix A sentence on page index 19, rendered the `GV.OC` pipe row, and removed the
full running header. SP 1299 parsed all 8 pages, and SP 800-53r5 parsed 492 pages in 49.412 seconds.
All 19 Python files passed byte-level ASCII decoding.

### Phase 1 checkpoint — what the system actually gets wrong

The roadmap's checkpoint says to ask it several questions and note the failures, because
those failures are what Phases 3 and 4 exist to fix. Seven questions over the OWASP corpus
(llama3.2, k=20). **Five answered well. Two failure modes are real and reproducible.**

**1. It hallucinated. This is the important one.**
`"What does AC-2 require?"` returned, with `refused=False`:

> "AC-2 requires that access control enforces policy such that users cannot act outside of
> their intended permissions."

AC-2 is a NIST SP 800-53 control and the Phase 1 corpus is OWASP Top 10 only. Confirmed
`"AC-2"` appears in **none** of the retrieved chunks — the model invented a plausible
answer from adjacent access-control text. This is exactly the spec requirement
("avoid generating information not present in the documents") failing, and prompt-only
grounding did not stop it.

**The good news: the T-4.2 gate would catch it.** Top retrieval score was **0.5685**,
comfortably below the 0.654-0.684 threshold band derived at T-1.6. That is independent
evidence the confidence gate is the right fix, and a real data point for calibrating it.

**2. It mislabelled a category even with correct context.**
Asked for the Top 10 list, it returned "A03:2021-Insecure Design". A03 is Injection;
Insecure Design is A04. The context was present and correct, so this is small-model
sloppiness rather than retrieval failure. T-4.1's inline citations make this kind of error
checkable by the reader instead of invisible.

**3. Latency is 3x the research estimate, and the cause is measured.**
Mean 19.1 s per answer (min 15.0, max 23.2) against RESEARCH.md section 9's predicted
3-5 s. Latency scales almost linearly with `k`:

| k | latency | context used |
|---|---|---|
| 5 | 5.2 s | 23% of `num_ctx` |
| 10 | 8.9 s | 47% |
| 20 | 15.0 s | 92.4% |

At k=5 the system hits the predicted 3-5 s exactly. So this is not a slow stack, it is
Phase 1 sending the whole retrieval pool to the model because there is no reranker yet.
T-3.5 narrowing 20 -> `rerank_top_n` (5) should recover roughly 3x on latency **and** drop
context pressure from 92% to 23%. That makes the reranker a latency fix as much as a
quality fix, which was not obvious before measuring.

**What works:** indexing (100 chunks, 4.1 s), semantic retrieval on paraphrase, multi-part
answers, and clean refusal on clearly out-of-corpus questions.

---

## Notes

- Phase 2 tasks get pulled in here once Phase 1's checkpoint passes.
- Record the Phase 3 baseline metrics the moment T-3.2 runs — everything after is measured against them.
- Any correction from the user → append the pattern to `tasks/lessons.md`.
