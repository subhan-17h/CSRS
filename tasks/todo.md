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
- [ ] **T-1.3** Naive recursive chunker (~400 tok / ~60 overlap)
- [ ] **T-1.4** ⚠ Embeddings with `search_document:` / `search_query:` prefixes + unit tests
- [ ] **T-1.5** Chroma store with `hnsw:space=cosine`, own embeddings passed in
- [ ] **T-1.6** Grounded generation + literal refusal string
- [ ] **T-1.7** `Pipeline` facade (`index()`, `ask()`)
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
_not started_

---

## Notes

- Phase 2 tasks get pulled in here once Phase 1's checkpoint passes.
- Record the Phase 3 baseline metrics the moment T-3.2 runs — everything after is measured against them.
- Any correction from the user → append the pattern to `tasks/lessons.md`.
