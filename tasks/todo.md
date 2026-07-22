# tasks/todo.md

Active work tracker. Full plan: [ROADMAP.md](../ROADMAP.md).

**Status:** Phases 0, 1, and 2 complete and verified. Next: Phase 3 retrieval quality.

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
- [x] **T-2.2** Structure-aware chunking with embedded hierarchy breadcrumbs
  - [x] Detect markdown, numeric, control, enhancement, and CSF headings with a depth stack.
  - [x] Emit page-local blocks so a chunk's page number is never ambiguous.
  - [x] Carry the breadcrumb into the embedded text via `Chunk.embed_text`, keeping `text`
    clean for display, and switch `Pipeline.index()` to embed it.
  - [x] Reject table-of-contents dot leaders; rebuild CSF labels from the match; cap labels
    at 80 characters.
  - [x] Prove lint, offline tests, CSF metrics, one SP 800-53 parse, and ASCII source/tests.
  - Verified: ruff clean, 54 offline tests pass on a dead Ollama port. SP 800-53 gives 1820
    chunks with `control_id` on 92.1%, 0 dot-leader breadcrumbs, and AC-2 resolving to
    `NIST.SP.800-53r5.pdf > ACCESS CONTROL > AC-2 ACCOUNT MANAGEMENT` at page 46. CSF
    breadcrumbs went from 72/244/263 to 72/114/147 characters and from 120 non-ASCII to 0.
  - ⚠ Known defect, deliberately NOT patched: every CSF breadcrumb carries a false ancestor,
    `Subcategories that were relocated in CSF 2.0.`. Traced to the source line
    `1.1 Subcategories that were relocated in CSF 2.0.` on page 19 -- a numbered **table
    caption** that the numeric-section pattern reads as a depth-2 heading, which then
    persists on the stack for the rest of the document. It is not a legitimate heading.
    A measured one-line fix exists (reject numeric headings whose label ends in a period:
    rejects exactly this caption, keeps all 62 SP 800-53 numeric headings) but was left
    unwritten because the parser is being replaced -- see below.
  - **Decision — the regex heading layer is being superseded.** Four rounds of heuristics
    across T-2.1/T-2.2 each fixed a real defect and each was found only by testing against
    a document the previous round had not seen. That is the signature of a corpus-tuned
    approach, and it works against the spec's "extensible to new standards" requirement.
    Docling's DocLayNet layout model classifies `Page-header`, `Page-footer` and
    `Section-header` structurally and suppresses furniture by construction, which replaces
    the whole T-2.1 furniture fix and the fragile numeric-section detection. Control-ID
    regexes (`AC-2`, `GV.OC-01`) stay either way -- no layout model knows NIST numbering.
    Cost, from Docling's own benchmark: 1.27-1.34 pages/s on an M3 Max versus the 9.5
    pages/s measured here, so SP 800-53 goes from 52 s to roughly 6 min, plus a GB-scale
    model warm-up. T-2.3's incremental indexing and T-2.5's progress UI both mitigate that
    and are already on the roadmap. This commit is the working fallback if the migration
    does not hold up.

- [x] **T-2.3** Content-hash incremental indexing
  - [x] Enumerate supported source paths without parsing and hash source bytes with SHA-256.
  - [x] Persist an atomic relative-path manifest and recover from corrupt manifest data.
  - [x] Add per-document chunk deletion and whole-store document-name inspection.
  - [x] Skip unchanged files before parsing; update changed files and remove deleted files.
  - [x] Rebuild on manifest/store disagreement and support an explicit forced rebuild.
  - [x] Preserve total document/chunk summaries while reporting run activity counts.
  - [x] Cover unchanged, changed-content, identical-content rewrite, deletion, force, corrupt
    manifest, empty-store recovery, and fully-skipped document names offline.
  - [x] Prove lint, offline tests, Docling test, ASCII source/tests/scripts, repository status,
    and a measured sub-second skip-before-parse demonstration.
  - **Verified independently on the real corpus**, because the roadmap's "Done when" is a claim
    about *where* the hash check sits in the call order, and a passing test suite cannot tell
    "skipped before parsing" apart from "parsed, then discarded". The proof sabotages
    `DoclingParser.parse` to raise on the second run:

    | Run | Result |
    |---|---|
    | 1 — cold index | **309.2 s**, 4 documents, 2506 chunks, added=4 |
    | 2 — unchanged, `parse()` rigged to raise | **0.057 s**, skipped=4, **parse never called** -> 5404x |
    | 3 — rewrite identical bytes (mtime changes) | skipped=4, updated=0 — content, not mtime |
    | 4 — change one file's content | updated=1, skipped=3, 4.3 s |
    | 5 — delete a file | removed=1, its chunks gone, names correct |

    `document_names()` stayed correct after the fully-skipped run — the trap where an
    incremental no-op would blank the UI caption. Ruff clean, **79 offline tests** (62 + 17
    new), Docling test passes, ASCII OK.
  - Checked, not assumed: `set_empty_document_names` pops `hnsw:space` before
    `collection.modify()`, which looks like it would silently drop the cosine space that T-1.5
    exists to guarantee. Probed behaviourally with orthogonal unit vectors — scores stay
    `[1.0, 0.0]` before, after, and across a reopen from disk, so the space is genuinely
    immutable collection config and only the descriptive metadata dict changes. Not a bug.
  - ⚠ Follow-up (**refactor**): the `empty_documents` mechanism — three store methods that
    serialise a JSON array into Chroma collection metadata — exists only so `document_names()`
    includes documents that produced zero chunks. The manifest already lists every indexed
    document, so deriving names from it is simpler and needs no store API. Note the coupling
    before changing it: the consistency guard compares manifest names against
    `store.document_names()`, which is *why* zero-chunk documents had to be tracked at all.

- [x] **T-2.4** Model dropdown from installed Ollama models
  - [x] Share implicit `:latest` model-name normalization with `scripts/warm_models.py`.
  - [x] Expose ordered selectable, missing, and unreachable states through `Pipeline`.
  - [x] Populate the sidebar selector, pass its choice to `ask`, and show `Answer.model`.
  - [x] Cover model inventory behavior fully offline and run all required verification.
  - **Verified:** ruff clean; 86 offline tests and the Docling test pass; byte-level ASCII
    decode passes. The warm script still reports 6 of 6 required models present. The live
    facade returns all five supported LLMs in configured order with none missing. A Streamlit
    probe against port 9 renders the `ollama serve` remedy with no application exception.
  - **Architecture note — the card's literal steps were deliberately not followed.** T-2.4 says
    `ollama.list() -> filter -> st.selectbox`, which reads as calling Ollama from `app.py`.
    ROADMAP.md's own architecture section says the UI never touches Ollama directly, and
    "modular and maintainable" is a checkable spec requirement. So listing lives in
    `generation.py` (which already owns the client), `Pipeline.model_availability()` exposes it,
    and `app.py` consumes only the facade. Proven, not asserted:
    `grep -n "ollama" src/csrs/app.py` returns only the error string and the `ollama pull` hint —
    no import, no call.
  - **The T-0.2 trap was real and is now closed.** `ollama.list()` reports `llama3.2:latest` and
    `phi4-mini:latest` while `settings.supported_llms` names them untagged, so a naive
    intersection would have reported **two mandated models as missing** — the exact "list that
    lies" this card exists to prevent. Verified live: selectable comes back as
    `('llama3.2', 'qwen2.5:1.5b', 'gemma2:2b', 'phi4-mini', 'gemma4:e2b')`, missing `()`, in
    configured order. With Ollama down: `reachable=False` and both tuples empty, distinct from
    "reachable but nothing installed", and no exception escapes.
  - **"Done when: switching models changes which model answers" — demonstrated live** on a
    147-chunk OWASP index, same question to three models:

    | Requested | `Answer.model` | Result |
    |---|---|---|
    | `llama3.2` | `llama3.2` | answered (6.0 s) |
    | `qwen2.5:1.5b` | `qwen2.5:1.5b` | **refused (4.1 s)** |
    | `gemma2:2b` | `gemma2:2b` | answered (5.2 s) |

  - ⚠ **Finding for T-4.2 and T-6.1 — a false refusal, not a bug in this card.**
    `qwen2.5:1.5b` refused "What is Broken Access Control?", which is squarely *in* the OWASP
    corpus and which both other models answered from the same retrieved chunks. Retrieval was
    identical; only the generator changed. This is empirical confirmation of the comment in
    `config.py` that llama3.2 follows grounding instructions more reliably than the smaller
    models, and it is the failure mode the roadmap calls worse than the alternative — refusing
    a valid question looks broken. Two consequences: T-4.2 must calibrate its confidence gate
    against the **default** model rather than assuming behaviour transfers across the dropdown,
    and T-6.1's README should say plainly that the selector exposes models which will answer
    less reliably than the default.

- [x] **T-2.5** Restart and reload controls plus persisted document summary
  - [x] Replace the hash-only manifest with validated hash/page/chunk records while preserving
    atomic replacement and corrupt/old-format self-healing.
  - [x] Expose filename, chunk count, and honest optional page count through `Pipeline`, sorted
    by filename, without UI access to storage internals.
  - [x] Preserve incremental add/update/delete, forced rebuild, and manifest/store consistency
    recovery; remove Chroma empty-document metadata only if those guards remain exact.
  - [x] Add distinct sidebar document/model sections, incremental reload, an explicitly costly
    full rebuild control, cache clear before rebuild, rerun, and `st.status` progress.
  - [x] Extend offline manifest and pipeline coverage for records, TXT page counts, add/remove,
    force, old/corrupt manifests, and all T-2.3 recovery guarantees.
  - [x] Run every requested verification and a timed headless add-then-incremental-reindex proof.
  - **Two card instructions were deliberately overridden.**
    1. *The button must not clear the manifest.* The card says "clear manifest -> cache clear ->
       rebuild", which contradicts T-2.3's own rationale in the same document ("the Restart &
       Reload button is unusable if it re-embeds 400 pages every press"). Clearing the manifest
       **is** re-embedding everything: 309 s per press. The primary button now runs an
       *incremental* reindex, which already detects new, changed and deleted files, and a
       separate explicitly-labelled control does a true `force=True` rebuild. Following the card
       literally would have satisfied the spec on paper and been unusable in practice.
    2. *Page count is persisted, not guessed.* `Document.page_count` was computed at parse time
       and discarded. The tempting shortcut, `max(chunk.page)`, understates any document whose
       trailing pages produce no chunks. The manifest therefore stores a record per document
       (hash, page count, chunk count) and reuses T-2.3's existing invalid-manifest-rebuilds path
       instead of migration code.
  - **Verified independently.** Ruff clean, **94 offline tests** (86 + 8 new), Docling test
    passes, ASCII OK, and `grep` confirms `app.py` still reaches no backend directly.
    The spec scenario, run literally on a temp corpus containing one real PDF:

    | Step | Result |
    |---|---|
    | Cold index | CSF PDF `chunks=209 pages=32`, TXT `chunks=2 pages=None` |
    | Drop a new file in, reindex | `added=1 skipped=2` in **0.11 s**, listed and queryable |

    Page count is the real 32, not a chunk-derived guess, and TXT reports `None` rather than a
    dishonest 0. Cache-clear ordering was checked by reading `app.py`: `st.cache_resource.clear()`
    runs *before* the rebuild, then `st.rerun()` — the reverse order silently reuses the stale
    cached `Pipeline` and is invisible to unit tests because it only exists in Streamlit's rerun
    model.
  - **The `empty_documents` refactor was safe, and the guard got stronger.** Removing it was
    conditional on every T-2.3 guard surviving, so each was re-tested in a *separate process*
    (chromadb caches clients per path in-process, so same-process checks give false results —
    my first attempt reported a bogus pass for exactly that reason):

    | Guard | Result |
    |---|---|
    | Steady state | `skipped=2` |
    | `chroma_db/` deleted, manifest kept | **rebuilt** (`added=2`) |
    | Corrupt manifest | **rebuilt**, no exception |
    | Zero-chunk document indexed | listed with `chunks=0`, **no rebuild loop** across 3 runs |

    The guard now compares per-document *chunk counts* rather than name sets, so it also catches
    partial corruption that the old name-set comparison would have missed. Zero-chunk documents
    are excluded from that comparison, which is what makes the `empty_documents` Chroma-metadata
    hack unnecessary.
  - ⚠ Known limitation, not worth code: deleting `chroma_db/` *while the app is running* can
    leave chromadb's process-global client cache holding a stale handle, which surfaces as a
    readonly-database error. Restarting the app clears it. Deleting the index out from under a
    live process is not a supported operation.

- [x] **T-2.6** Sidebar application settings
  - [x] Thread an optional temperature from `Pipeline.ask()` to `generate_answer()`, preserving
    the configured default when callers omit it.
  - [x] Group model, `top_k`, temperature, and Ollama connection state as application settings.
  - [x] Cap the `top_k` control at 20 so Phase 2 cannot silently overflow Ollama's context.
  - [x] Add concise document/chunk totals while preserving the per-document list and both reload
    controls in a distinct indexed-documents section.
  - [x] Cover explicit/default temperature forwarding and unchanged model/`k` behavior offline.
  - [x] Prove lint, offline and Docling tests, ASCII, UI/backend isolation, captured Ollama
    options, headless HTTP serving, and repository status.
  - **Verified:** ruff clean; 96 offline tests and the Docling test pass; Python source, tests,
    and scripts decode as ASCII. The UI boundary grep contains only Ollama-facing copy and
    facade result fields, with no backend import, Chroma access, or manifest access. A live
    temporary index reported Ollama reachable and captured generation client temperatures
    `[0.0, 1.0]` from two `Pipeline.ask()` calls. The headless Streamlit app returned HTTP 200
    and was stopped cleanly.

- [x] **T-2.7** Docling as the default PDF parser *(absorbs T-5.3; supersedes the T-2.1
  furniture heuristics and the T-2.2 numeric-heading regex)*
  - [x] **S1** `DoclingParser` behind config, with `PdfParser` kept as a selectable fallback.
    - [x] Add lazy, cached Docling conversion with pinned offline artifacts and guarded
      one-pass page splitting.
    - [x] Resolve the configured PDF parser at call time while leaving TXT ingestion intact.
    - [x] Cover registry switching, split guards, actionable setup failures, and the CSF corpus.
    - [x] Prove lint, offline tests, Docling corpus behavior, pypdf fallback, and ASCII source.
      Verified independently, not taken from the handoff's self-report: ruff clean (the UP033
      `lru_cache(maxsize=None)` it left behind was resolved with ruff's own autofix to
      `@cache`), **59 offline tests pass** on a dead Ollama port (54 pre-existing + 5 new),
      byte-level ASCII decode OK, `CSRS_PDF_PARSER=pypdf` selects `PdfParser` while the
      default selects `DoclingParser`, and the `docling`-marked CSF test passes in 15.8 s.
      Two extra proofs beyond the brief: importing `csrs.loaders` leaves **`docling` absent
      from `sys.modules`**, so the lazy import is real rather than assumed; and pointing
      `CSRS_DOCLING_ARTIFACTS_PATH` at a missing directory raises `DoclingSetupError` with
      the `docling-tools models download` remedy instead of a stack trace.
    - Cached converter (model load is one-time), `artifacts_path` pinned to
      `~/.cache/docling/models` so the runtime never fetches, `do_ocr=False` (the corpus is
      digital-native; this also avoids needing the EasyOCR weights at all).
    - One `export_to_markdown(page_break_placeholder=...)` pass, split into `Document.pages`;
      `escape_html=False` and an empty image placeholder so `&amp;` and `<!-- image -->` stay
      out of retrieval text.
    - Missing package or missing weights must fail with the remedy (`docling-tools models
      download`, or `CSRS_PDF_PARSER=pypdf`), not a stack trace.
    - **Done when** the CSF sample yields 32 pages with the running header gone, the GV.OC
      table renders as a Markdown table, `CSRS_PDF_PARSER=pypdf` still reproduces T-2.1
      behaviour, and the existing suite passes.
  - [x] **S2** Collapse the chunker's heading layer onto real Markdown headings.
    - [x] Classify ATX labels by content, preserve raw control/enhancement/CSF matching, and
      remove dotted numeric headings.
    - [x] Resolve bare enhancement IDs from the nearest stacked control without treating
      colon-terminated field labels as structural headings.
    - [x] Cover Markdown controls, bare enhancements, field labels, and raw CSF IDs offline.
    - [x] Measure both cached Markdown exports and run the required lint, test, and ASCII proofs.
    - ⚠ **Revised after measuring the real SP 800-53 Markdown — this is NOT the simple
      deletion the plan assumed.** That assumption came from CSF alone. SP 800-53 breaks it:
      | Measured on Docling's SP 800-53 Markdown | Count |
      |---|---|
      | Total headings, **all at flat `##`** | 1075 |
      | Controls, `## AC-2 ACCOUNT MANAGEMENT` | 322 |
      | Enhancements, `## (1) TITLE ...` (**not** `AC-2(1)`) | 303 |
      | Generic field labels, `## Control:` / `## Control Enhancements:` | 274 |
    - Consequences the implementation must handle:
      1. **Markdown depth is useless for hierarchy.** Every heading is `##`, so taking depth
         from the marker makes each heading pop the previous one. Depth has to come from what
         the heading *is* (control vs enhancement vs section), not from how many `#` it has.
      2. **Field labels must not reset control context.** `## Control:` follows
         `## AC-2 ACCOUNT MANAGEMENT`; if it is treated as a sibling heading, every chunk of
         AC-2's actual control text gets the breadcrumb `... > Control:` and loses `AC-2`.
      3. **Enhancements carry no parent.** `## (1) ACCOUNT MANAGEMENT | ...` needs the
         enclosing control from the heading stack to become `AC-2(1)`; the existing
         `_enhancement_heading` regex expects `AC-2(1)` inline and will never match.
    - ⚠ **Accepted regression, to be settled by measurement not opinion.** T-2.2's breadcrumb
      was `... > ACCESS CONTROL > AC-2 ACCOUNT MANAGEMENT`. That `ACCESS CONTROL` came from
      SP 800-53's *running page header*, which Docling correctly classifies as furniture and
      drops — it never appears as a heading (42 occurrences, 0 as `^## ACCESS CONTROL`). The
      family name could be restored with a 20-entry `AC -> ACCESS CONTROL` lookup, but that is
      exactly the corpus-tuned hardcoding this task exists to remove, and the roadmap's rule is
      measure before optimising. **Deferred to T-3.2:** if the eval harness shows family-level
      breadcrumbs matter, add the map then, with evidence.
    - **Done when** SP 800-53 `control_id` coverage is restored to ~92% (it is **0.0%** if the
      Markdown pattern is left to match first), an enhancement chunk resolves to `AC-2(1)`,
      no AC-2 chunk has `Control:` as its terminal breadcrumb, and CSF false-ancestor
      breadcrumbs stay at 0.
    - **Verified independently** (re-measured against the cached Docling exports, not taken
      from the handoff's report):

      | Gate | Result |
      |---|---|
      | SP 800-53 `control_id` | 1670/1853 = **90.1%**, up from 0.0% |
      | Breadcrumbs ending `Control:` | **0** |
      | Enhancement resolution | `AC-2(1)`, breadcrumb `... > AC-2 ACCOUNT MANAGEMENT > (1) ACCOUNT MANAGEMENT | AUTOMATED SYSTEM ACCOUNT MANAGEMENT` |
      | CSF `control_id` | 160/206, **up** from 128 |
      | CSF false ancestors | **0** |

      Plus ruff clean, **62 offline tests** pass on a dead Ollama port (59 + 3 new), the
      `docling` test passes, and ASCII decode is clean.
    - **On the 90.1% vs T-2.2's 92.1%:** this is not a shortfall. All 183 chunks without a
      `control_id` are content that legitimately has no control to attribute -- Errata (67),
      Table of Contents (20), `2.2 CONTROL STRUCTURE AND ORGANIZATION`, `Executive Summary`,
      `INTRODUCTION`. The two percentages are also over different chunk populations (1853
      Docling chunks vs 1820 pypdf chunks), so they were never directly comparable. 90.1% is
      the correct ceiling for this corpus rather than a regression to chase.
  - [x] **S3** `scripts/warm_models.py` so the weights are a deliberate, documented step.
    - Pulled forward from T-5.3; T-3.5 needs the same script for FlashRank, and T-6.3's
      offline proof depends on it existing.
  - [x] **S4** Move `docling` to core dependencies and correct the documents that say otherwise.
    - `pyproject.toml` (out of `[project.optional-dependencies]`), `OS_REPOS.md` §3
      (currently records pypdf-primary/Docling-optional — this reverses it), `ROADMAP.md`
      T-5.3 marked absorbed by T-2.7.
    - Note for **T-6.2**: `uv export` must now include Docling, and the T-5.3 gotcha "the
      grader shouldn't be made to install Docling" no longer holds — it is the default path.
    - `tasks/lessons.md` gains **L-4** for the correction that started this: four rounds of
      corpus-tuned heuristics, each fixing a real defect found only by testing against a
      document the previous round had not seen, is the signal to reach for a structural tool
      rather than write a fifth rule.
    - Verified: `uv lock --check` in sync, `uv sync` clean, `import docling` works with no
      extra, no `[project.optional-dependencies]` group remains, ruff clean, 62 offline +
      1 Docling test pass. Reviewer correction on top of the handoff: the risk register's
      "first index is slow" row was still rated Medium against the old ~52 s figure, and is
      now **High** with the measured 336 s.

  ### Live end-to-end proof (real Ollama, real corpus)

  Everything above is unit tests and offline measurement against cached Markdown. This is the
  whole chain — Docling parse -> structure-aware chunking -> `nomic-embed-text` -> Chroma ->
  `llama3.2` — run for real: **4 documents, 2506 chunks, 336.3 s** to index.

  **The Phase 1 checkpoint hallucination is fixed.** `What does AC-2 require?` previously
  returned an invented sentence with `refused=False`, because the corpus was OWASP-only and
  the top score was 0.5685. It now returns AC-2's actual lettered requirements a. through j.,
  including NIST's own `[Assignment: organization-defined ...]` notation, citing
  `page=47 control_id=AC-2` and `page=46 control_id=AC-2` at scores 0.6726 / 0.6707.

  **S2's enhancement hierarchy earns its keep.** `What must an organization do for automated
  system account management?` retrieves at **0.8420** with
  `control_id=AC-2(1)` and breadcrumb
  `NIST.SP.800-53r5.pdf > AC-2 ACCOUNT MANAGEMENT > (1) ACCOUNT MANAGEMENT | AUTOMATED SYSTEM ACCOUNT MANAGEMENT`.
  That id exists only because bare `(1)` headings resolve against the nearest stacked control.

  Cross-document retrieval works (the six CSF Functions answered correctly from SP 1299 p.2
  *and* CSWP 29 p.2), and the negative control held: `What is the capital of France?` returned
  `refused=True` with the exact configured refusal string.

  **Page citations verified with a different library.** Trusting Docling to check Docling
  proves nothing, so the cited pages were re-read with `pypdf`: PDF pages 46 and 47 both
  contain `AC-2` and `ACCOUNT MANAGEMENT`, page 47 contains the automated-mechanisms
  enhancement text, and SP 1299 page 2 contains all six Function names. **The placeholder
  page-split carries no off-by-one**, which would otherwise have silently corrupted every
  citation in the system. That check also re-confirmed the T-2.1 decision to cite 1-based PDF
  position rather than the printed number: PDF page 46 prints "PAGE 19".

  ⚠ **The 336 s is paid on every app start until T-2.3 lands.** `Pipeline.index()` still does
  a full rebuild, so the Streamlit app currently looks frozen for over five minutes on launch.

  **Spike evidence (measured 2026-07-22, before any code was written).** docling 2.114.0,
  docling-core 2.87.1, weights 1.2 GB in `~/.cache/docling/models`.

  | Question | Answer |
  |---|---|
  | Does it suppress furniture structurally? | Yes. `page_header`/`page_footer` items land in `ContentLayer.FURNITURE`, and `export_to_markdown` emits `BODY` only. |
  | Does every item carry a page number? | Yes — `items lacking page provenance: 0` on both PDFs tested. |
  | Can we still build `Document.pages`? | Yes. `export_to_markdown(page_break_placeholder=...)` in **one** pass splits into exactly `len(doc.pages)` segments, byte-identical to per-page `export_to_markdown(page_no=n)` calls on all 8 SP 1299 pages. |
  | Does the known CSF defect go away? | **Yes, structurally.** `1.1 Subcategories that were relocated in CSF 2.0.` was never a caption — it is a *wrapped sentence* (`...gaps in numbering indicate CSF 1.1 Subcategories that were relocated in CSF 2.0.`). Docling reflows the paragraph, so the line the regex tripped on no longer exists. |
  | Are tables better? | Yes. Table 1 renders as a real Markdown table with a `Category Identifier` column, versus T-2.1's flat pipe rows. |
  | Speed | **1.99 pages/s** — SP 800-53's 492 pages in 246.8 s (4.1 min). |

  **The full SP 800-53 run settles the cost question in Docling's favour.** 1.99 pages/s is
  ~1.5x faster than Docling's own 1.27-1.34 M3 Max benchmark, so the estimate in the T-2.2
  note above (~6 min) was pessimistic. It classified **1937 furniture items** (982
  `page_header`, 955 `page_footer`) into `ContentLayer.FURNITURE`, alongside 1075
  `section_header`, 101 `table` and 0 items lacking page provenance. Both strings that took
  T-2.1 four rounds of heuristics to kill — `NIST SP 800-53, REV. 5 ... SECURITY AND PRIVACY
  CONTROLS` and the per-page `CHAPTER THREE PAGE <n>` stamp — are absent from the body
  Markdown with no rule written for either. The residual `CHAPTER THREE` (4) and
  `doi.org/10.6028` (120) hits were inspected and are all legitimate content: a dot-leader
  TOC row, the real `## CHAPTER THREE` heading, the title-page availability line, and the
  errata table that literally lists DOI corrections.

  **The chunker already works on Docling output, unmodified.** Feeding the real CSF
  Markdown through the current `chunk_document` gives 207 chunks, `control_id` on 128, and
  **0 breadcrumbs carrying the false ancestor** — down from 133/133. That makes S2 a
  deletion, not a rewrite, which is why this migration is worth doing now rather than at T-5.3.

  ⚠ **S2 has a silent regression waiting in it — measured, not theorised.** Docling emits
  control headings as real Markdown (`## AC-2 ACCOUNT MANAGEMENT`), so the ATX pattern matches
  *first* and returns `control_id=None`:

  ```
  _match_heading("## AC-2 ACCOUNT MANAGEMENT") -> (2, 'AC-2 ACCOUNT MANAGEMENT', None)
  _match_heading("AC-2 ACCOUNT MANAGEMENT")    -> (4, 'AC-2 ACCOUNT MANAGEMENT', 'AC-2')
  ```

  Run over the real Docling SP 800-53 Markdown, the current chunker yields 2068 chunks with
  `control_id` on **0.0%**, against T-2.2's 92.1% baseline. Nothing fails loudly — breadcrumbs
  still look right — but exact-ID retrieval loses its metadata entirely. So S2 must **take
  depth from the Markdown marker and then re-match the stripped label against the domain
  control patterns** for `control_id`, rather than returning on first pattern hit.
  `control_id` coverage on SP 800-53 is the acceptance number for S2, not chunk count.

  **Fallback policy (decided).** `PdfParser` stays selectable, and the raw-text heading
  heuristics are deleted with it degrading honestly — the fallback still parses, chunks and
  answers, with thinner breadcrumbs. It is an emergency path, not a supported quality tier,
  and the failure message must say so.

  ⚠ **Consequence for T-2.3 — this is the load-bearing one.** Docling is roughly an order of
  magnitude slower than pypdf, so the manifest must hash **the source file's bytes and
  short-circuit before `parse()` is called**. Hashing chunks, or hashing after parsing, still
  pays the full Docling cost on every run and leaves "Restart & Reload" unusable. T-2.3 was
  a convenience before; it is now what makes the default path affordable.

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

**T-2.7 S2:** Reclassified flat Docling ATX headings from their labels: controls use depth 4,
bare enhancements use depth 5 and inherit the nearest stacked control, field labels ending in a
colon remain body text, and other Markdown headings use depth 6 beneath recognized domain
structure. Removed dotted numeric headings while preserving raw control, enhancement, and CSF
matching. Cached SP 800-53 Markdown produced 1853 chunks with `control_id` on 1670 (90.1%), an
`AC-2(1)` enhancement, and zero terminal `Control:` breadcrumbs. Cached CSF Markdown produced 206
chunks with `control_id` on 160 and zero relocated-caption breadcrumbs. Ruff passed, 62 offline
tests passed, the Docling-marked test passed, and Python source/tests passed byte-level ASCII decode.

**T-2.3:** Added deterministic supported-path enumeration so source bytes are SHA-256 hashed
before parser invocation. A relative-path JSON manifest is replaced atomically; corrupt data and
manifest/store disagreement trigger a rebuild. Changed and removed documents are deleted by
`doc_name`, while Chroma collection metadata preserves zero-chunk document state for complete
consistency checks and document listings. Duplicate basenames are rejected because the existing
Chunk/Document identity contract cannot represent them safely. `IndexResult` now reports run
activity while its original fields remain current index totals, and `force=True` rebuilds all
sources. Ruff passed; 79 offline tests and the one Docling test passed; byte-level ASCII decoding
passed. A two-TXT throwaway proof replaced `TextParser.parse` with a failure before the second run:
the run still reported `skipped=2` and completed in 0.001140 seconds, directly proving the parser
was not called.

**T-2.5:** The manifest now stores a strict hash, page count, and chunk count record per relative
source path. `Pipeline.documents()` exposes sorted summaries, including `page_count=None` for TXT,
and the sidebar renders them separately from the existing model selector. The primary reload clears
Streamlit resources before an ordinary incremental index; the separately labelled full rebuild uses
`force=True` and warns about its roughly five-minute corpus cost. Both paths run inside `st.status`
and rerun with the newly cached Pipeline. Old hash-only manifests are deliberately invalid under the
new validator, so the next index performs a one-time full reparse; there is no migration because no
manifest has been deployed. Corrupt JSON remains non-raising and atomic temp-file replacement remains
intact.

The Chroma `empty_documents` metadata array was removed. The consistency guard now compares exact
positive per-document chunk counts from the manifest and store, which preserves empty-store and
partially-missing recovery, detects wrong counts even when a document name remains present, and lets
zero-chunk documents live honestly in the manifest. Verification: ruff clean; 94 dead-port offline
tests pass (86 before this card); the Docling test passes; byte-level ASCII decode passes; and the UI
boundary grep shows no Chroma or manifest access. A throwaway two-TXT proof added `second.txt` after
the first index: the incremental result was `added=1, updated=0, skipped=1, removed=0`, the list grew
from one document to two, a public query retrieved `second.txt`, and reindexing took 0.003005 seconds.

**T-2.6:** The sidebar now separates application settings, indexed-document details, and document
controls. Settings include the installed-model selector, a `top_k` slider capped at the measured
Phase 2 context limit of 20, a temperature input, and explicit Ollama connected/disconnected state.
The document section adds total document and chunk counts without removing its persisted per-file
details, and both reload paths remain unchanged. Temperature is an optional facade and generation
argument with the configured default preserved at both layers; no UI state enters backend modules.
Verification: ruff clean; 96 dead-port offline tests and the Docling test pass; ASCII decode and the
UI boundary check pass. A live temporary index captured client temperatures `[0.0, 1.0]` from two
facade calls, and the headless app returned HTTP 200 before being stopped.

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
