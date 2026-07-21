# tasks/todo.md

Active work tracker. Full plan: [ROADMAP.md](../ROADMAP.md).

**Status:** Phase 0 complete and verified. Phase 1 is next.

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
- [ ] **T-1.8** 🎉 Minimal Streamlit app — **first end-to-end answer**

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

### Phase 1

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

---

## Notes

- Phase 2 tasks get pulled in here once Phase 1's checkpoint passes.
- Record the Phase 3 baseline metrics the moment T-3.2 runs — everything after is measured against them.
- Any correction from the user → append the pattern to `tasks/lessons.md`.
