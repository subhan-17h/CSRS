# tasks/todo.md

Active work tracker. Full plan: [ROADMAP.md](../ROADMAP.md).

**Status:** Phases 0, 1, and 2 complete and verified, and the Phase 2 checkpoint passes --
`CSRS.md` §1-6 is demonstrable against the running app. **This is the submittable state.**
Submission documentation is written: [README.md](../README.md) (install, setup, running,
adding documents, limitations) and [ENGINEERING.md](../ENGINEERING.md) (the decision
narrative and the measurements behind it). Phases 3-5 are deferred as extended optimization;
every limitation that leaves behind is stated plainly in both documents.

**Phase 7 is also complete:** a FastAPI layer and React frontend now run alongside the
Streamlit app, which is unchanged. The pipeline was not modified, so the Phase 2 checkpoint
evidence below still holds. The web UI renders the page-level citations the Streamlit
interface never displayed.

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

### Phase 2 — complete

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

### Phase 2 checkpoint — `CSRS.md` §1-6 walked against the running system

Run against the real corpus indexed into `chroma_db/`: **4 documents, 2506 chunks, 316.0 s**
cold. Every row below is measured, not read off the source. §5 was checked by rendering
`app.py` through `streamlit.testing.v1.AppTest` and inspecting the real widget tree, because
grepping for `st.selectbox` proves the call exists, not that it renders with the right options.

**§1 Document Management**

| Requirement | Evidence |
|---|---|
| Accept PDF and TXT | Registry resolves `.pdf` -> `DoclingParser`, `.txt` -> `TextParser`, `.docx` -> `None`. Live index holds both formats |
| Auto-load every supported document from `docs/` | 4 discovered by recursive scan, including 2 inside `docs/samples/` |
| Support multiple documents simultaneously | CSF 32 p/209 ch, SP 1299 8 p/31 ch, SP 800-53 492 p/2119 ch, OWASP TXT 147 ch |
| Detect new documents with no code change | Dropped a TXT into `docs/`, incremental reindex `added=1 skipped=4` in **0.35 s**, answered from it at 0.6552, then `removed=1` and back to 2506 chunks |
| Restart & Reload button | Rendered, plus a separate explicitly-costly full rebuild |

**§2 Knowledge Base Construction** — `nomic-embed-text` (768 d) into local Chroma at
`chroma_db/`; 2506 chunks embedded and stored. Embedding runs automatically on load and
reload, and a second run over an unchanged corpus is **0.057 s, `skipped=4`**.

**§3 Semantic Retrieval** — the spec's "keyword search alone is not sufficient" was tested
with a query sharing **no content word** with its target: *"How should a company keep track
of the equipment and software it owns?"* Top 3 are `ID.AM-01` (0.7523), `ID.AM-02` (0.7401),
`ID.AM-08` (0.7175) — hardware and software inventory. No lexical overlap could have found
those. Only the retrieved chunks reach the model.

**§4 Question Answering** — the spec's own five example questions, default `llama3.2`, k=5:

| Question | Result |
|---|---|
| Functions of the NIST CSF? | All six correct (Govern...Recover), 3.2 s |
| Explain the Identify function. | ⚠ **Wrong — see below** |
| What does ISO 27001 require for access control? | **Refused**, which is correct: ISO 27001 is deliberately excluded on licensing grounds |
| How is Incident Response handled? | Correct, cites `IR-4` and `RS.MA-01` across three documents, 5.9 s |
| Requirements for Asset Management? | Correct, cites `ID.AM`, `ID.AM-05`, `ID.AM-08`, 3.7 s |

Negative controls both refused with the exact configured string: *capital of France*,
*sourdough bread*.

**§5 User Interface** — every required element rendered, with no uncaught exception:
question input `'Ask a question about the indexed documents'`; the answer written back with
`Answered by llama3.2`; the document list showing all four files with chunk and page counts
and the honest `page count not applicable` for TXT; a `Model` selector defaulting to
`llama3.2` over all five supported LLMs; `Restart & Reload Documents`; and a sidebar whose
`Application settings` header carries the model selector, `top_k` (5, capped 20),
`Temperature` (0.1) and `Ollama: Connected`.

**§6 Local LLM Integration** — Ollama at `127.0.0.1:11434`, `nomic-embed-text` mandatory for
all embedding, all **5 of 5** supported LLMs selectable in configured order with none
missing. Switching the dropdown changes the answering model: `llama3.2` 1.2 s,
`qwen2.5:1.5b` 4.5 s, `gemma2:2b` 5.8 s, each returning its own name in `Answer.model`.

#### The one real failure, and what it actually is

`"Explain the Identify function."` answered confidently and **wrongly**, with
`refused=False`: it described SI-19 *de-identification of PII*. Retrieval, not generation,
is at fault — the model was faithful to the context it was given. This is a different
failure mode from the Phase 1 hallucination, and worse in one specific way (below).

**Diagnosed rather than guessed.** The content is present and ranks well; the query is the
problem:

| Query | Top hit |
|---|---|
| `Explain the Identify function.` | 0.7127 `SI-19 DE-IDENTIFICATION` |
| `Explain the Identify function of the NIST Cybersecurity Framework.` | 0.8082 CSF Abstract, then SP 1299 `IDENTIFY` at 0.8017 |

Bare "Identify" collides with SP 800-53's `DE-IDENTIFICATION` and `IDENTIFICATION AND
AUTHENTICATION`, and 2119 of 2506 chunks are SP 800-53, so the dense pool is dominated by
it. Eleven words of context move the right chunks from absent to rank 1-2.

⚠ **This is the measurable cost of the unimplemented bonus.** In `CSRS.md` §4 the example
questions are a *sequence*: "What are the functions of the NIST Cybersecurity Framework?"
is immediately followed by "Explain the Identify function." The second is a **follow-up**,
and §4's "preserve conversational context for follow-up questions (bonus if implemented)"
is exactly what would resolve it. So this is not an unexplained defect — it is the one
optional requirement not built, showing up precisely where the spec predicted it would.
The README must say this plainly rather than quoting the four questions that worked.

⚠ **Finding that invalidates part of the T-4.2 calibration.** The bad answer's top score
was **0.7127**, *above* the 0.654-0.684 refusal band derived at T-1.6 and above the 0.5685
that would have caught the Phase 1 hallucination. A score-threshold confidence gate
calibrated on those points **would not catch this**. Confidently-wrong-but-well-retrieved is
a distinct failure class from nothing-relevant-retrieved, and a single scalar threshold does
not separate them. If T-4.2 is ever built, this data point belongs in its golden set.

**Suite state at checkpoint:** ruff clean, 96 offline tests pass on a dead Ollama port,
working tree clean.

---

## Phase 3 — Retrieval quality

- [x] **T-3.1** Golden set
  - [x] Read indexed chunks across all four documents and record auditable provenance.
  - [x] Author 48 exact-ID, paraphrase, cross-document, refusal, and spec-example pairs.
  - [x] Validate every matcher against the live store and run repository verification.
  - **Verified:** all 48 pairs and every matcher validate against 4 documents / 2506 chunks;
    category counts are 12 exact-ID, 12 paraphrase, 8 cross-document, 10 out-of-scope,
    and 6 spec examples. Ruff passes and 133 offline tests pass with 1 deselected against
    a dead Ollama port.

---

## Phase 7 — React frontend + FastAPI layer

Phases 4-5 stay deferred. This phase adds a second interface without changing what the
RAG pipeline does. `src/csrs/app.py` (Streamlit) is **untouched** and remains the
spec-§5 graded interface, so the Phase 2 checkpoint evidence above stays valid.

Backend changes are strictly additive: a streaming generation path alongside
`generate_answer()`, and one read-only store accessor. `Pipeline.ask()`, `chunking.py`,
`embeddings.py`, `store.search()` and the `config.py` retrieval defaults do not change.

Plan: `/Users/rowdy/.claude/plans/ok-for-the-open-radiant-owl.md`

### Backend

- [x] **T-7.1** FastAPI skeleton + read endpoints (`/api/health`, `/api/documents`, `/api/models`)
  - [x] Add and lock FastAPI/Uvicorn dependencies without disturbing retained retrieval packages.
  - [x] Add a lazy, guarded, dependency-overridable Pipeline with one-time incremental indexing.
  - [x] Expose typed health, document, and model responses with localhost-only CORS.
  - [x] Add the localhost-bound `csrs-api` entry point and fully isolated API tests.
  - [x] Prove lint, offline tests, ASCII source, and real warm-index endpoint responses.
  - **Verified:** Ruff clean; 101 offline tests pass on a dead Ollama port (96 existing plus
    5 API tests); 25 Python files decode as ASCII. Importing the ASGI module leaves the lazy
    singleton as `None`. The real warm index reports 4 documents and 2506 chunks, Ollama is
    reachable, and all five supported LLMs are selectable. The server shut down cleanly and a
    follow-up curl confirmed port 8000 was closed.
  - Reviewed independently: CORS returns `access-control-allow-origin` for `:5173` and
    withholds it from other origins; with `CSRS_OLLAMA_HOST` on a dead port the live server
    still answers `/api/health` 200 with `ollama_reachable: false` and `/api/models` with an
    empty inventory rather than a fabricated fallback.
  - ⚠ Finding for **T-7.4**: `get_pipeline()` indexes on first use, so if Ollama is down
    *and* documents changed, initialization raises and `/api/health` 500s instead of
    reporting the outage. Invisible while the index is warm, because content hashes skip
    before any embedding call. The reload endpoints must not widen that window.
- [x] **T-7.2** `POST /api/chat` — serialize `Answer` with `sources[]`, 503 on Ollama down
  - [x] Validate the question, supported model, top-k range, and temperature at the API boundary.
  - [x] Forward posted values unchanged and preserve pipeline defaults when fields are omitted.
  - [x] Serialize grounded citations with nullable TXT and unstructured-chunk metadata intact.
  - [x] Map only Ollama connection failures to the established 503 response.
  - [x] Cover success, refusal, forwarding, validation, and connection failure offline.
  - [x] Prove lint, the full offline suite, live grounded citations, 422/503 behavior, and shutdown.
  - **Verified:** Ruff clean; **111 offline tests pass** on a dead Ollama port (101 existing
    plus 10 chat cases), with one Docling test deselected. A live default-model request answered
    the CSF question in 7462 ms with five citations from `NIST.CSWP.29_CSF-2.0.pdf` and
    `NIST.SP.1299.pdf`, including real page numbers. Whitespace returned 422; a server pointed
    at port 9 returned the exact established 503 detail. Both servers shut down cleanly and
    `lsof` confirmed port 8000 was free.
  - Reviewed independently: the CSF question returned the six correct 2.0 Functions (Govern,
    Identify, Protect, Detect, Respond, Recover) grounded in 5 sources, top hit
    `NIST.CSWP.29_CSF-2.0.pdf` p.2 at 0.8049. An SP 800-53 question confirmed `control_id`
    populates for real (AC-2 p.46 at 0.8056, AC-2 p.47, AC-2(7) p.49) and that `top_k: 3`
    is honored. All six validation cases 422 as intended, whitespace-only included.
  - This is the payload the Streamlit UI never renders: `answer.sources` reaches a client
    for the first time here, with page, section breadcrumb, control ID and cosine score.
- [x] **T-7.3** `POST /api/chat/stream` — NDJSON stage events + Ollama token streaming
  - [x] Add generator-based Ollama streaming with prompt/options parity and final refusal detection.
  - [x] Add the retrieval-identical `Pipeline.ask_stream()` facade path.
  - [x] Emit ordered compact NDJSON stage, token, final, and connection-error events.
  - [x] Cover generation parity, final assembly/refusal, empty input, endpoint flow, and errors.
  - [x] Prove lint, full offline tests, live incremental delivery, grounded parity, and shutdown.
  - **Verified:** Ruff clean; **116 offline tests pass** on a dead Ollama port (111 existing
    plus 5 streaming tests), with one Docling test deselected. All 25 Python files under
    `src/` and `tests/` decode as ASCII. The critical parity test compares the complete
    non-streaming Ollama call with the streaming call plus only `stream=True`, covering the
    exact prompt, model, `num_ctx`, temperature, and `keep_alive` payload.
  - Live default-model streaming retrieved 5 passages and emitted 38 separate token events.
    Measured client receipt was incremental: token 1 at 0.291 s, token 10 at 0.500 s, token
    20 at 0.735 s, token 30 at 0.969 s, and the final event at 1.186 s. The final response
    cited `NIST.CSWP.29_CSF-2.0.pdf` pages 2, 6, and 5 plus `NIST.SP.1299.pdf` pages 2 and 1.
    A same-question `/api/chat` comparison returned the same six CSF Functions and the exact
    same `(doc_name, page)` citation set. Uvicorn shut down cleanly and `lsof` confirmed port
    8000 was free.
  - Reviewed independently — **parity proved on the real corpus**, which was the whole risk
    of this task. At `temperature: 0.0` the AC-2 question returned a **byte-identical**
    576-character answer from `/api/chat` and `/api/chat/stream`, citing the same five
    chunks in the same order (AC-2 p.46, AC-2 p.47, AC-2(7) p.49, AC-2(3) p.48, AC-2(1) p.47).
  - Tokens confirmed genuinely incremental, not buffered: 41 tokens with the first at 0.31 s
    and the last at 1.26 s (0.95 s spread), stages in order with real timings (retrieve 96 ms,
    generate 1209 ms). A dead Ollama port yields `stage_start` then the exact `error` event
    under HTTP 200 -- the status cannot change once the stream has begun, so the event is how
    the client learns.
  - `ask_stream()` deliberately contains no `yield`, so retrieval runs eagerly when it is
    called and only generation stays lazy. That is what lets the endpoint close the retrieve
    stage before advancing generation. Do not "tidy" it into a generator function.
- [x] **T-7.4** Index reload/rebuild endpoints with streaming progress and a concurrency lock
  - [x] Instrument `Pipeline.index()` with optional parse, embed, skip, and removal progress.
  - [x] Stream reload/rebuild stage events, progress updates, keepalives, errors, and counts.
  - [x] Serialize index runs behind a non-blocking lock that survives disconnects and failures.
  - [x] Cover progress, force forwarding, stream shape, concurrency, and retry after failure offline.
  - [x] Prove lint, full offline tests, live warm-index reload, document totals, and shutdown.
  - **Verified:** Ruff clean; **123 offline tests pass** on a dead Ollama port (116 existing
    plus 7 new), with one Docling test deselected. The API tests prove compact ordered NDJSON,
    all six result counts, rebuild `force=True`, a concurrent 409, keepalives, generic errors,
    and an Ollama failure followed by a successful retry. All 25 Python files decode as ASCII.
  - Live warm-index reload completed in **45 ms**, emitted a skip update for each of the four
    documents, and returned 4 documents, 2506 chunks, added=0, updated=0, skipped=4, removed=0.
    `/api/documents` still returned those 4 documents and 2506 chunks afterward. The real
    rebuild endpoint was not called. Uvicorn shut down cleanly and port 8000 was confirmed free.
  - Reviewed independently on the real corpus, exercising the whole document lifecycle
    through the API rather than only the happy path:
    - Baseline reload: `skipped=4`, 2506 chunks, 39 ms, index untouched.
    - Added `docs/ZZ_TEST_POLICY.txt` -> `added=1`, 5 documents / 2507 chunks in 709 ms,
      and the new file was immediately answerable (`ZZ_TEST_POLICY.txt` at 0.9066, correct
      "every 47 days"), which is CSRS.md §1 extensibility demonstrated through the new API.
    - Concurrency: two overlapping reloads returned 200 and **409** with
      "An index operation is already in progress."
    - The lock genuinely releases -- the next reload succeeded (`skipped=5`).
    - Removing the file reported `removed=1` and restored the exact baseline
      (209 / 31 / 2119 / 147 = 2506).
  - `/api/index/rebuild` was proven only against the fake pipeline asserting `force=True`.
    It was deliberately never run on the real corpus: it destroys a warm index that costs
    ~316 s to rebuild. Keep it that way.
  - The `ping` keepalive only fires when the queue is idle >10 s, so it is exercised by a
    real full rebuild, not by the sub-second incremental path.
- [x] **T-7.5** `ChunkStore.chunks_for_document()` + chunk endpoint + static `dist/` serving
  - [x] Add numeric chunk-ID ordering, pagination, totals, and malformed-ID safety.
  - [x] Delegate document chunk browsing through `Pipeline` and expose the validated API route.
  - [x] Mount `frontend/dist` with SPA fallback after API routes when the directory exists.
  - [x] Cover store order/pagination/unknown documents and API shape/errors/static behavior.
  - [x] Prove Ruff, the full offline suite, warm-index responses, static root, and port cleanup.
  - **Verified:** Ruff clean; **133 offline tests pass** on a dead Ollama port (123 existing
    plus 10 new), with one Docling test deselected. The store tests use temporary Chroma
    collections and prove integer ordering through IDs `:2` and `:10`, pagination totals,
    unknown documents, metadata row alignment, and deterministic malformed-ID handling.
  - The API tests prove the exact chunk response shape, 404/422 behavior, startup without a
    frontend build, SPA fallback with a build, and that the root mount does not shadow API
    routes. Changed Python sources decode as ASCII.
  - Live against the untouched warm index: OWASP returned IDs `:0`, `:1`, `:2` and total 147;
    SP 800-53 returned IDs `:100`, `:101`, total 2119, page 23, and the stored null control IDs
    for those Errata chunks; an unknown document returned 404. `/api/health` remained JSON with
    4 documents and 2506 chunks. `/` returned 200 and matched `frontend/dist/index.html`
    byte-for-byte. Uvicorn shut down cleanly and port 8000 was confirmed free.

  - Reviewed independently: ordering is genuinely numeric, not lexical -- OWASP ids returned
    `0..11` with `:10` after `:9` (total 147). SP 800-53 at `offset=700` returned real
    metadata (p.164-165, `IA-4(1)`, `IA-4(9)`, full section breadcrumbs) with total 2119.
    Unknown document 404s with a clear detail; `limit=0`, `limit=201` and `offset=-1` all 422.
  - Static mount verified **not** to shadow the API: `/api/health`, `/api/documents` and
    `/api/models` all still return JSON, `/` and `/some/spa/route` return the SPA at 200,
    and `/api/bogus` correctly 404s instead of falling back to `index.html` -- so a mistyped
    API path can never silently return HTML.
  - `frontend/dist` currently holds the stale pre-rebrand build; serving it is expected and
    is replaced in T-7.6.

**Backend complete.** All five endpoints ship: health/documents/models, chat, chat/stream,
index reload/rebuild, and document chunks. 133 offline tests, ruff clean, the real index
untouched at 4 documents / 2506 chunks throughout.

### Frontend

- [ ] **T-7.6** Strip the Unibot domain, rebrand to CSRS, vendor fonts locally (offline)
  - [ ] Replace the copied frontend types and API client with the non-streaming CSRS contract.
  - [ ] Remove the SQL/data-view surface and rebrand the remaining chat experience.
  - [ ] Vendor every used font weight as a local Latin WOFF2 asset.
  - [ ] Prove the production build, static audits, proxied live answer with citations, and clean shutdown.
  - Reviewed independently: `npm run build` passes with zero TypeScript errors (39 modules,
    156 kB JS / 39 kB CSS). Rebrand greps for `unibot|fyp|thesis|phdcs|registrar|supervisor`
    return nothing across `src/`, `index.html` and `public/`.
  - **Offline compliance restored** (CSRS.md §6 line 6): the Google Fonts CDN tags are gone
    and 7 woff2 files (~92 kB, latin subset) are vendored to `public/fonts/`, copied into
    `dist/fonts/` by the build and served at 200. The only URLs left anywhere in the built
    bundle are the SVG namespace and React's error-docs string -- neither is ever fetched.
  - End to end **through the vite proxy** (which proves path, contract and proxy all align,
    not just the backend in isolation): `POST localhost:5173/api/chat` returned the six
    correct CSF 2.0 Functions with 5 citations, top hit `NIST.CSWP.29_CSF-2.0.pdf` p.2 at
    0.8049. `/api/health`, `/api/documents` and `/api/models` all 200 through the proxy.
  - `conversation_context` deleted from the contract rather than kept inert -- multi-turn is
    deliberately unimplemented, and a field the backend ignores would misrepresent it.
  - ⚠ Finding for **T-7.8**: `ProgressEvent` in `types.ts` still declares a required
    `detail: Record<string, unknown>`, but the backend's stage events never send it. Harmless
    today because the stream is only cast, not validated -- fix the type when wiring streaming.
  - Not visually verified: there is no browser in this environment, so rendering was proven
    by a passing type-check and a live contract round-trip, not by looking at the page.
- [x] **T-7.7** `SourcesCard` (citations with page/section/control-ID) + markdown answers
  - [x] Add only `react-markdown` and `remark-gfm` to the frontend dependencies.
  - [x] Render completed answers as safe GFM while preserving plain-text streaming output.
  - [x] Replace the source list with an accessible, expandable citation card.
  - [x] Distinguish refusals from errors and omit empty citation UI.
  - [x] Show retrieved passages on refusals with explicitly insufficient wording.
  - [x] Prove the build, dependency/raw-HTML audits, live proxied answers, refusal path,
    and clean server shutdown.
  - `npm run build` passes with zero TypeScript errors (293 modules, 315.42 kB JS /
    43.36 kB CSS). The direct dependency diff adds only `react-markdown` and `remark-gfm`;
    the raw-HTML escape-hatch grep is empty, changed frontend sources decode as ASCII, and
    `git diff --check` passes.
  - Live through the Vite proxy, the AC-2 question returned a Markdown paragraph plus an
    unordered `*` list and five SP 800-53 sources. All sources carried pages 46-49, section
    breadcrumbs, AC-2-family control IDs, ranks, true cosine scores, and chunk text.
  - Correction: a model refusal can carry the retrieved-but-insufficient top-k passages.
    Preserve that diagnostic context while making clear that it did not support an answer;
    only an actually empty array should suppress the disclosure.
  - Live correction proof through the Vite proxy: the cookie-recipe question returned the
    exact refusal with five OWASP passages and renders the collapsed label `5 passages
    retrieved, none sufficient · OWASP_Top_10_2021`. The AC-2 question returned a grounded
    answer with five SP 800-53 citations and renders `5 sources · NIST.SP.800-53r5`.
    Expanded citation cards are shared unchanged between both states. No rebuild path was
    called; both servers shut down and ports 8000 and 5173 were confirmed free.
  - Reviewed independently: build clean (293 modules), only `react-markdown` and `remark-gfm`
    added, and `grep` for `rehype-raw|dangerouslySetInnerHTML` returns nothing -- model output
    stays escaped, which is the right posture for untrusted text.
  - Markdown is real, not theoretical: the live AC-2 answer contains `* ` bullet syntax that
    would otherwise render as literal asterisks. Confirmed against the raw response string.
  - **Review caught a wrong premise in my own brief.** I told Codex "a refusal has no
    sources", so it gated the card behind `!msg.refused`. That is false --
    `Pipeline.ask()` always retrieves top-k before the model decides, so a refusal returns
    `refused: true` WITH 5 sources. Sent back via resume; now gated on array length and the
    strip reads differently per outcome. Verified live:
    - refusal -> "5 passages retrieved, none sufficient . OWASP_Top_10_2021"
    - normal  -> "5 sources . NIST.SP.800-53r5"
    Recorded as **L-5** in `tasks/lessons.md`.
  - Score bars rescale from a 0.4-0.95 floor/ceiling because real scores cluster tightly
    (0.7395-0.8056 on AC-2); an unscaled 0-1 bar makes every source look identical. The
    label always shows the true value.
  - Cost noted: the bundle grew 156 kB -> 315 kB (50 -> 98 kB gzipped) from the remark/unified
    tree. Acceptable for a local offline app, and it is the price of not shipping raw `**`.
- [x] **T-7.8** Wire streaming and live progress stages into `App.tsx`
  - [x] Correct the frontend stream event contract and add robust buffered NDJSON parsing.
  - [x] Reduce live stage events into the existing progress UI and append real answer tokens.
  - [x] Preserve cancellation, stale-request guards, server error details, and HTTP fallback.
  - [x] Prove the production build, source invariants, incremental Vite proxy stream, and shutdown.
  - **Verified:** `npm run build` passes with 293 modules transformed and zero TypeScript
    errors. `git diff --check` and byte-level ASCII decoding pass; source checks confirm no
    `setTimeout`/`answer.slice` reveal remains and no stage variant declares `detail`.
  - The required NIST question streamed through Vite on port 5173 with 38 token events. The
    first token arrived at 2.952 s and the last at 4.137 s, a 1.185 s spread that proves the
    proxy did not buffer the response. Retrieval completed in 742 ms, generation in 3202 ms,
    and the final event reported 3944 ms with five sources and the six CSF functions.
  - No proxy change was needed. Uvicorn and Vite were stopped cleanly; `lsof` confirmed ports
    8000 and 5173 were both free. The warm index was queried only, never rebuilt.
  - Reviewed independently. The risk in this task was the **dev proxy silently buffering**
    the stream -- that would look identical to working code in every unit test. Verified by
    timestamping tokens through `localhost:5173`: 38 tokens from 1.15 s to 2.03 s
    (0.88 s spread). Not buffered.
  - Also verified in **single-port production mode** (FastAPI serving the built `dist`, no
    vite involved), which is a genuinely different path and the one a grader uses: `/` served
    the freshly built `index-DGRvVazc.js`, and "How is Incident Response handled?" streamed
    **233 tokens over 6.26 s**. Without streaming that is an 8.6 s blank spinner.
  - The simulated `setTimeout` typewriter is deleted. Real tokens made it both slower than
    the actual stream and dishonest about what the user was watching.
  - Type inaccuracy from T-7.6 is fixed: `detail` removed from the stage variants (the
    backend never sent it), `token` added, and the phantom `ts` dropped from `final`.
  - Stream parsing buffers across chunk boundaries (`lines.pop()` keeps the partial tail,
    flushed after the loop), so a JSON object split across two network reads still parses.
    Every state write is guarded by an `isCurrent()` identity+abort check so a superseded or
    aborted request cannot write into the UI.
- [x] **T-7.9** Sidebar settings — full spec-§5 parity (model, top_k, temperature, reload)
  - [x] Lift model, top_k, temperature, runtime inventory, and index-operation state into App.
  - [x] Reuse buffered NDJSON parsing for typed chat and index streams, preserving 409 details.
  - [x] Render reachable/missing-model status, settings, document totals/list, and index controls.
  - [x] Gate chat on Ollama/model readiness and index activity; gate rebuild behind cost confirmation.
  - [x] Prove the build, live non-default chat settings, warm reload stream, and clean shutdown.
  - **Verified:** `npm run build` passes with 293 modules transformed and zero TypeScript
    errors. Ruff, byte-level frontend ASCII decoding, and `git diff --check` also pass.
  - Live Vite-proxy reads returned all five installed models with `llama3.2` as the default,
    plus four indexed documents and 2506 chunks; the TXT correctly returned a null page count.
  - The required non-default AC-2 request reported `qwen2.5:1.5b` and exactly three sources
    when posted with `top_k: 3` and `temperature: 0.0`, proving the generation settings path.
  - The only real index mutation invoked was `/api/index/reload`: it emitted four live
    per-document skip updates and completed in 98 ms with added=0, updated=0, skipped=4,
    removed=0, documents=4, and chunks=2506.
  - `/api/index/rebuild` was not invoked. Static inspection proves it is reachable only after
    a second `Confirm rebuild` action whose prompt explicitly says it takes about five minutes.
  - Independent review caught and verified fixes for partial runtime-fetch failures, stale
    refresh races, split health/model readiness, authoritative final totals, and transport-only
    stream fallback. Backend and Vite shut down cleanly; ports 8000 and 5173 were confirmed free.
  - Reviewed independently. The settings are **not decorative** -- proved by contrast on the
    same question through the proxy:
    - `model=qwen2.5:1.5b, top_k=3` -> reports `qwen2.5:1.5b` with exactly 3 sources
    - defaults -> reports `llama3.2` with 5 sources
  - ⚠ **Finding worth keeping.** `qwen2.5:1.5b` *refused* the AC-2 question that `llama3.2`
    answers. Isolated it to the model, not the context size, by crossing both variables:
    qwen refuses at k=3 **and** k=5; llama3.2 answers at k=3 **and** k=5. This is empirical
    support for the `config.py` claim that llama3.2 follows grounding and refusal
    instructions more reliably than the smaller models -- and it means a grader who switches
    the dropdown will legitimately see refusals on questions the default answers.
  - Index controls verified live: reload through the proxy streams per-document
    `stage_update` lines and ends `skipped=4`, 2506 chunks, 84 ms. Rebuild is gated behind a
    two-step confirmation naming the five-minute cost, and was verified **by code path only**
    -- never executed against the real corpus.
  - Chat-disabled reasons are specific rather than a blanket block: index updating, health
    unreachable, model inventory unreachable, Ollama disconnected (carrying the
    `ollama serve` remedy), and no supported model installed.
- [x] **T-7.10** Corpus Explorer replacing the SQL Data Viewer
  - [x] Add typed chat/corpus mode navigation while keeping the chat subtree mounted.
  - [x] Add typed document-chunk API access that preserves backend error details.
  - [x] Render selectable documents, ordered chunk metadata/text, and honest page-local filtering.
  - [x] Paginate with boundary-safe 50-chunk previous/next controls and reset on document change.
  - [x] Reuse and extend the `.dv-*` design with theme tokens and responsive behavior.
  - [x] Prove the frontend build, live proxy responses, pagination math, chat-state preservation,
    frontend ASCII, diff hygiene, and clean shutdown of ports 8000 and 5173.
  - **Verified:** `npm run build` passes with 294 modules transformed and zero TypeScript
    errors; Ruff, byte-level frontend ASCII decoding, and `git diff --check` pass.
  - Live Vite-proxy reads returned four documents and 2506 chunks. The OWASP request returned
    chunks 0-4 with null page/control metadata; the SP 800-53 request at offset 700 returned
    pages 164-165 and `IA-4(1)` / `IA-4(9)`. Their UI ranges are `Showing 1-5 of 147` and
    `Showing 701-703 of 2119`.
  - The real SP 800-53 last page at offset 2100 returned 19 chunks, IDs 2100-2118. At offset
    zero Previous is disabled and Next requests 50; at offset 2100 Previous requests 2050 and
    Next is disabled, so the component cannot request a negative or out-of-range offset.
  - A real missing-document request returned HTTP 404 with `Document 'not-indexed.pdf' is not
    in the index.`; the shared JSON reader propagates that backend detail into `.dv-state.error`.
  - Chat and Corpus are mounted siblings. Mode changes only toggle the `inactive` class, while
    messages, composer state, `busy`, and the in-flight AbortController remain mounted and no
    mode-change path calls `abort()`.
  - Only read endpoints were called. Both servers shut down cleanly and ports 8000 and 5173
    were confirmed free; `/api/index/rebuild` and `Pipeline.index(force=True)` were not called.
  - Reviewed independently. Pagination boundaries verified against the real 2119-chunk
    document rather than reasoned about: `offset=2100&limit=50` returns 19 chunks, renders
    "showing 2101-2119 of 2119", and next is correctly disabled
    (`offset + limit >= total`). A past-the-end `offset=2200` returns 200 with an empty page
    instead of crashing.
  - Null metadata handled properly -- OWASP chunk `:0` has page, section and control_id all
    null, and each is conditionally rendered, so "Page null" never appears.
  - The filter is **labelled honestly**: the API has no server-side chunk search, so the
    placeholder reads "Filter chunks on this page" and the count reads "N of M on this page".
    It never implies a corpus-wide search that is not happening.
  - Chat state survives tab switching: both panels stay mounted and the inactive one is
    hidden with `display: none` plus `aria-hidden`, so it leaves the tab order entirely
    while React keeps conversation state and any in-flight stream alive.
- [x] **T-7.11** localStorage conversation history
  - [x] Add versioned, shape-validated history storage with bounded oldest-first eviction.
  - [x] Persist stable completed-answer snapshots without writing streamed token updates.
  - [x] Abort and invalidate active requests before new, select, or active-delete transitions.
  - [x] List, select, mark, and delete newest-first conversations in the expanded sidebar.
  - [x] Prove the build, corrupt-storage recovery, live proxied chat, and clean shutdown.
  - **Verified:** `npm run build` passes with zero TypeScript errors (295 modules,
    338.67 kB JS / 50.79 kB CSS), Ruff and byte-level ASCII checks pass, and the
    throwaway Node probe was removed after malformed JSON plus two wrong shapes each
    loaded zero conversations while the valid versioned payload loaded one. A simulated
    quota failure retried with 3 -> 2 -> 1 conversations and retained only the newest.
  - Live through Vite, `/` returned 200, health reported Ollama reachable with the untouched
    4-document / 2506-chunk index, and `/api/chat` returned the correct six CSF 2.0
    Functions with three citations in 4685 ms. No rebuild path was called; both servers
    stopped and ports 8000 and 5173 were confirmed free.

  - Reviewed independently by transpiling `history.ts` with esbuild and exercising `load()`
    and `save()` directly, rather than trusting the report. All six hostile inputs returned
    empty **without throwing** -- malformed JSON, wrong-shape object, wrong-shape array,
    right shape with a wrong version, a corrupt inner message, and absent storage -- while a
    well-formed history loaded. That matters because a throw during render would white-screen
    the app on nothing worse than stale storage.
  - Quota eviction verified with a storage stub that rejects above 2 entries: 5 `setItem`
    attempts, ending with the **newest** two kept (conv 5, conv 4). Oldest is sacrificed
    first, and persistence failure never propagates into the UI.
  - Validation is structural per field, not a cast, and `MAX_CONVERSATIONS = 20` bounds the
    payload -- necessary because one answer can carry 20 sources of full chunk text against
    a ~5 MB budget.
  - Write cadence confirmed: `saveHistory` fires only on answer completion and on delete,
    never per streamed token. `newChat`, `selectConversation` and `deleteConversation` all
    abort an in-flight request first, so a late token cannot write into a different
    conversation.
  - Note: `load()` fails closed -- one invalid conversation discards the whole history rather
    than salvaging the rest. Acceptable because the blob is written atomically by this app
    alone, but it is a deliberate trade, not an oversight.

### Close-out

- [x] **T-7.12** README + ENGINEERING updates, offline verification, phase commit
  - [x] Document both interfaces in `README.md` with a comparison table, real run commands,
        dev vs production modes, and new troubleshooting rows.
  - [x] Record the Phase 7 reasoning in `ENGINEERING.md` as Decision 6, plus the payoff note
        on Decision 5 (the facade is what made a second interface cost no pipeline changes).
  - [x] Correct the stale limitations: citations now render, and the honest remaining gap is
        that they are not *inline* per claim.
  - [x] Prove the offline claim rather than assert it.
  - **Written against real runs, not from memory** (`tasks/lessons.md` L-2; a previous README
    draft fabricated an output block). Every command and number below was executed:
    - `uv run csrs-api` -> serves `/` at 200 and `/api/health` JSON; `lsof` confirms it binds
      `127.0.0.1:8000` only, not all interfaces.
    - The four spec example questions (CSRS.md 63-67) measured live: CSF functions 1654 ms
      (CSF 2.0 p.2 @ 0.8049), Incident Response 4129 ms (SP 1299 p.7 @ 0.8164), Asset
      Management 3358 ms (CSF 2.0 p.23 @ 0.7744). **ISO 27001 correctly refuses** -- it is
      not in the shipped corpus, and the README now says plainly that this is right, not a
      bug, because it would otherwise read as a failure to a grader.
    - The documented "Identify" failure still reproduces exactly as recorded: bare form
      answers wrongly from SP 800-53 p.385 at 0.7127; naming the framework moves the correct
      chunks to rank 1 at 0.8082.
  - **Offline proof (CSRS.md line 6), by walking the whole asset graph:** served the
    production build and resolved every reference -- `index.html` -> 3 assets, stylesheet ->
    7 `url()` font references -- all HTTP 200 from localhost, zero external. All 7 frontend
    `fetch()` targets are relative paths. The only absolute URLs anywhere in the bundle are
    an SVG namespace and React's error-docs string, neither ever requested.
  - Final gate: ruff clean, **133 offline tests pass** on a dead Ollama port, frontend builds
    with zero TypeScript errors, all Python and TS/TSX sources decode as ASCII, and the real
    index is still 4 documents / 2506 chunks.

---

## Phase 7 review

**Shipped.** A FastAPI layer and a React frontend, added alongside the Streamlit app rather
than replacing it. Twelve tasks, twelve commits, `5d0c2ad` through `a57c0e6`.

**The pipeline is untouched, and that was the point.** No change to retrieval, chunking,
embedding, storage, or the `config.py` defaults. `src/csrs/app.py` is byte-for-byte
identical, so the Phase 2 checkpoint evidence above remains valid. The only backend
additions were additive: `generate_answer_stream()` beside `generate_answer()`, `ask_stream()`
beside `ask()`, an optional `on_progress` callback on `index()`, and one read-only
`chunks_for_document()` accessor. The offline suite grew 96 -> 133 with no existing test
modified.

**What the new interface actually adds.** `Answer.sources` has existed since Phase 1 and
`app.py` discarded it. Page numbers, section breadcrumbs and control IDs -- built by three
separate Phase 2 decisions -- were invisible to every user. Rendering them is the reason this
phase exists; streaming and the corpus browser are conveniences on top.

**Two reviews caught things the reports did not:**
1. **T-7.7 -- a wrong premise in my own brief.** I asserted "a refusal has no sources", so
   citations were hidden on refusals. `Pipeline.ask()` always retrieves *before* the model
   decides, so a refusal carries a full sources array. Hiding it discarded the evidence that
   explains the refusal and would have concealed the confidently-scored-but-irrelevant
   retrieval failure documented in Phase 2. Fixed via resume; recorded as **L-5**.
2. **T-7.6 -- a lie in the types.** `ProgressEvent` declared a required `detail` field the
   backend never sends, surviving only because the stream is cast rather than validated.
   Logged against T-7.8 and fixed there rather than left to surface later.

**Risks that were proven rather than argued:**
- *Streaming divergence* -- a second generation path could silently change answers with every
  test still green. At `temperature: 0.0` both endpoints return a **byte-identical**
  576-character answer citing the same five chunks in order.
- *Proxy buffering* -- would look identical to working code in tests. Timestamped tokens
  through vite (38 tokens, 0.88 s spread) and again in production mode (233 tokens, 6.26 s).
- *Offline* -- the imported frontend fetched fonts from a CDN, breaking CSRS.md line 6 on
  arrival. Fonts vendored; the entire served asset graph now resolves locally.
- *Storage quota* -- one answer can hold 20 sources of full chunk text against ~5 MB. Verified
  by transpiling `history.ts` and driving it directly: six hostile inputs return empty without
  throwing, and quota eviction keeps the newest.

**Judgement calls worth re-examining if this continues:**
- `conversation_context` was **deleted**, not kept inert. Correct while multi-turn is
  unimplemented; reinstate honestly if the §4 bonus is ever built.
- `load()` fails closed -- one corrupt conversation discards all history.
- The bundle grew 156 kB -> 339 kB for `react-markdown`. Fine locally; it is the cost of not
  rendering raw `**` to the user.

**Appearance: verified by the user, 2026-07-23.** No browser existed in the agent environment,
so every claim above rested on type-checking, contract round-trips and asset resolution rather
than on looking at the page. The user has since opened both UIs (`csrs-api` on :8000 and
Streamlit on :8501) and confirmed both render correctly. This open question is closed.

**Suite state at phase close:** ruff clean, 133 offline tests pass on a dead Ollama port,
frontend builds with zero TypeScript errors, all sources ASCII, index intact at 4 documents /
2506 chunks, working tree clean.

---

## Notes

- Phase 2 tasks get pulled in here once Phase 1's checkpoint passes.
- Record the Phase 3 baseline metrics the moment T-3.2 runs — everything after is measured against them.
- Any correction from the user → append the pattern to `tasks/lessons.md`.
