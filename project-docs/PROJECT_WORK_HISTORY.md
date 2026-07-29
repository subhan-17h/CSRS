# CSRS Project Work History

## Overview

I built CSRS, a local retrieval-augmented generation system for cybersecurity standards,
between July 21 and July 29, 2026. The repository has a linear history of 85 commits by
`subhan-17h`, with no merges. Across those commits, Git records 38,741 insertions and 7,705
deletions.

The project grew from a Python walking skeleton into a page-aware document pipeline with
hybrid retrieval, grounded Ollama generation, Streamlit and React interfaces, and a
50-question evaluation across five local models. The shipped corpus is NIST Cybersecurity
Framework 2.0, indexed as 209 chunks from 32 pages.

## How this record was verified

This history uses the canonical Git log and each commit's message, changed files, and diff.
Implementation claims were checked against the current source, tests, manifests, and final
evaluation artifacts. The original [specification](CSRS.md), [roadmap](ROADMAP.md),
[research](RESEARCH.md), [task record](../tasks/todo.md), and
[lessons](../tasks/lessons.md) provide context, but planned or superseded work is not
presented as current functionality.

Commit timestamps show when work was recorded, not the hours spent. The modified
`eval/final/summary.csv` and untracked root `RAG_Evaluation_Report.pdf` and `results.md`
were excluded because they are outside the canonical committed history.

## Work by day

### July 21 - Foundation and first working RAG

I established the specification, research, roadmap, Python 3.12 `uv` project, corpus
workflow, and typed settings. I then completed the first end-to-end path: loaders,
recursive chunking, prefixed Ollama embeddings, Chroma storage, grounded generation, a
pipeline facade, and a minimal Streamlit UI. The day ended with page-preserving PDF
parsing, boilerplate removal, and hierarchy-aware chunks.

**23 commits; +10,212 / -1,101 lines.**

### July 22 - Production ingestion and web application

I replaced the growing PDF heuristics with Docling, added model warming for offline use,
and used Docling headings in chunk metadata. Content hashes made unchanged indexing fast,
while model selection, reload controls, and runtime settings completed the Streamlit
requirements. I then added FastAPI endpoints and began a React interface with grounded
citations and streamed retrieval progress.

**18 commits; +10,629 / -426 lines.**

### July 23 - Frontend completion and hardening

I completed token streaming, application settings, the corpus explorer, and local browser
conversation history. I documented and visually verified both interfaces, fixed corrupt
history handling so one bad conversation could not erase the rest, documented process
shutdown, and introduced the first 48-question retrieval golden set.

**11 commits; +3,399 / -255 lines.**

### July 24 - Retrieval quality, conversation context, and submission

I added retrieval metrics, persisted BM25 search, reciprocal-rank fusion, and optional
FlashRank reranking. Measurements showed that the original Recall@10 and nDCG@10 targets
rewarded duplicate control chunks, so I corrected the evaluation focus and made hybrid
retrieval the default. I also added conversational query rewriting, original-document
viewing, licensing, submission documentation, and a final live-application audit.

**22 commits; +5,380 / -796 lines.**

### July 28 - Evidence-grounded answer evaluation

I replaced the legacy retrieval-only harness with EVAL-2: 20 readable questions over four
documents, cosine similarity, retrieval evidence coverage, and an optional structured
Groq GPT-OSS judge. The completed two-model run established an answer-quality baseline.

**1 commit; +4,177 / -1,856 lines.**

### July 29 - CSF-only five-model evaluation

I reduced the durable corpus to CSF 2.0 and created 50 new evidence-grounded questions.
EVAL-3 added CPU BERTScore alongside cosine similarity and the GPT-OSS judge, compared all
five installed Ollama models, and produced detailed resumable reports. I corrected
non-atomic benchmark claims, made quota-window resumes safe, normalized CSV output, and
published a complete 250-row run with no technical errors.

**10 commits; +4,944 / -3,271 lines.**

## Major implementation stages

| Stage | Result |
|---|---|
| Foundation | Specification, research, configuration, corpus workflow, and typed contracts. |
| Local RAG | Page-aware loading, structured chunks, Ollama embeddings and generation, and Chroma persistence. |
| Retrieval quality | Incremental indexing, BM25 plus dense RRF, optional reranking, and query rewriting. |
| Interfaces | Streamlit for the required UI; FastAPI and React for streaming chat and corpus browsing. |
| Evaluation | Legacy retrieval checks evolved into EVAL-2 and then the CSF-only, three-metric EVAL-3 benchmark. |

## Complete commit ledger

The ledger below accounts for every commit in the canonical history. Diff totals above are
computed from these commits; unreachable rewrite, amend, and stash objects are not separate
delivered changes.

| Date | Commit | Subject | Verified effect |
|---|---|---|---|
| 2026-07-21 | [`603d1a0`](https://github.com/subhan-17h/CSRS/commit/603d1a09be49836d86ab64367f27f68f9bdf87db) | chore: initialise repository with spec and planning artefacts | Added the specification, research, roadmap, and repository guidance. |
| 2026-07-21 | [`d50914a`](https://github.com/subhan-17h/CSRS/commit/d50914a9881b05d0e95195d0f60e07fe130c37de) | chore(T-0.1): scaffold uv project on Python 3.12 | Created the Python package, dependencies, and lockfile. |
| 2026-07-21 | [`f883f1c`](https://github.com/subhan-17h/CSRS/commit/f883f1c4488fe69e6f7721dfb2b8daf573d2b4b7) | feat(T-0.3): add corpus fetch script and public-domain sample | Added the standards fetcher and initial text sample. |
| 2026-07-21 | [`5dad583`](https://github.com/subhan-17h/CSRS/commit/5dad583d62155206f28fcba91df590d782ee1608) | feat(T-0.4): add typed settings module | Centralized runtime settings with typed environment configuration. |
| 2026-07-21 | [`78a3884`](https://github.com/subhan-17h/CSRS/commit/78a3884f287050774b3eae7a0da859bfc90cd6cf) | docs(phase 0): close Phase 0 -- environment, models and corpus verified | Recorded verified Phase 0 completion evidence. |
| 2026-07-21 | [`e5c620d`](https://github.com/subhan-17h/CSRS/commit/e5c620d9e5e50918ecbfdd1bf8cffeea39988d13) | feat(T-0.4): default to llama3.2 rather than qwen2.5:1.5b | Changed the default chat model to Llama 3.2. |
| 2026-07-21 | [`68a94ab`](https://github.com/subhan-17h/CSRS/commit/68a94abafa4bba0e92a9721fde76a56261ba5c2d) | feat(T-0.3): ship one PDF and one TXT sample, each a different standard | Added NIST PDF and OWASP text samples. |
| 2026-07-21 | [`3d70c34`](https://github.com/subhan-17h/CSRS/commit/3d70c345402b7538eee893242c2450cfd314757f) | docs: forbid attribution trailers in commit messages | Recorded the repository ban on attribution trailers. |
| 2026-07-21 | [`67a9f21`](https://github.com/subhan-17h/CSRS/commit/67a9f21329388ba858f0859b7f52d5ddfce5fe80) | feat(T-1.1): add the data models every module exchanges | Defined shared document, chunk, retrieval, and answer models. |
| 2026-07-21 | [`bba6ec5`](https://github.com/subhan-17h/CSRS/commit/bba6ec5eebdcf6f93470fb4733f6be49d101632c) | docs: require a watcher on every Codex task | Added mandatory watcher workflow guidance and its lesson. |
| 2026-07-21 | [`436e267`](https://github.com/subhan-17h/CSRS/commit/436e2673b61e78b030658915232ffba7ffd74dd5) | feat(T-1.2): add DocumentParser protocol, TXT loader and registry | Implemented the parser protocol, registry, and TXT loader. |
| 2026-07-21 | [`09085e2`](https://github.com/subhan-17h/CSRS/commit/09085e2133908930be148510f7bd1d7d7f53a95e) | docs: make Codex keep tasks/todo.md current, and pin its constraints | Made task tracking and repository constraints explicit. |
| 2026-07-21 | [`5e0ab5f`](https://github.com/subhan-17h/CSRS/commit/5e0ab5fa5dec28dcc15ac54493007d4ed7956648) | feat(T-1.3): add naive recursive chunker with real text overlap | Implemented recursive chunking with tested overlap. |
| 2026-07-21 | [`647b16e`](https://github.com/subhan-17h/CSRS/commit/647b16e02c12a5157ddf07f06d4590eeeeeb3468) | docs: identify the Codex job before attaching a watcher | Required watcher setup to identify the active job. |
| 2026-07-21 | [`ce02e1f`](https://github.com/subhan-17h/CSRS/commit/ce02e1fcc4a490e7d324e9e9097a851a4cbccf9b) | feat(T-1.4): embed via Ollama with the mandatory nomic task prefixes | Implemented Ollama embeddings with Nomic task prefixes. |
| 2026-07-21 | [`16ee54a`](https://github.com/subhan-17h/CSRS/commit/16ee54ab6955925b1da16a3787a05bc56588306e) | feat(T-1.5): persist chunks in Chroma with cosine space and our own vectors | Persisted external embeddings and chunks in cosine Chroma. |
| 2026-07-21 | [`72a1843`](https://github.com/subhan-17h/CSRS/commit/72a1843a4e3d6a18c9e60e17175bf3244c293eba) | feat(T-1.6): generate grounded answers with a literal refusal string | Added grounded generation, sources, and refusal behavior. |
| 2026-07-21 | [`2a5f0a6`](https://github.com/subhan-17h/CSRS/commit/2a5f0a609c43f86347c9a12e47c20b2a464f93a2) | feat(T-1.7): add the Pipeline facade the UI and eval harness both drive | Introduced the shared indexing and query pipeline. |
| 2026-07-21 | [`e4e32a1`](https://github.com/subhan-17h/CSRS/commit/e4e32a1bd63c2bc19316f6635e7b9634af9ca803) | feat(T-1.8): add the minimal Streamlit app that closes the loop | Added the initial end-to-end Streamlit interface. |
| 2026-07-21 | [`fd56a5f`](https://github.com/subhan-17h/CSRS/commit/fd56a5fb2e15eb319ba34f32a91220c8a626017b) | docs(phase 1): close Phase 1 with the checkpoint findings | Recorded verified Phase 1 checkpoint results. |
| 2026-07-21 | [`f861318`](https://github.com/subhan-17h/CSRS/commit/f8613180a9ac6114ac8fd5d015a723236fe1b437) | feat(T-2.1): parse PDFs into page-preserving documents | Added page-preserving PDF parsing and tests. |
| 2026-07-21 | [`061ef52`](https://github.com/subhan-17h/CSRS/commit/061ef5258c266c25f6915f05050e6a880394d0b0) | fix(T-2.1): strip running boilerplate the full corpus actually has | Removed recurring PDF headers and footers. |
| 2026-07-21 | [`85a7735`](https://github.com/subhan-17h/CSRS/commit/85a773513638d7bff1cc1005f76728acc2d19f66) | feat(T-2.2): split on control boundaries and embed hierarchy breadcrumbs | Added control-boundary chunking and hierarchy breadcrumbs. |
| 2026-07-22 | [`0e45c98`](https://github.com/subhan-17h/CSRS/commit/0e45c98aa0027c3c3131d271341e8593798d3e42) | feat(T-2.7): add Docling as the default PDF parser behind config | Made configurable Docling parsing the PDF default. |
| 2026-07-22 | [`fee4fe7`](https://github.com/subhan-17h/CSRS/commit/fee4fe7aaabd7e8fa1891d322cf68a8108a08fc1) | feat(T-2.7): drive chunk hierarchy from Docling's Markdown headings | Derived chunk hierarchy from Docling headings. |
| 2026-07-22 | [`cb16167`](https://github.com/subhan-17h/CSRS/commit/cb1616731ff48f48dd81fc0f008f8804df0e9a72) | feat(T-2.7): add warm_models.py so offline operation is a setup step | Added model prewarming for offline operation. |
| 2026-07-22 | [`acf112a`](https://github.com/subhan-17h/CSRS/commit/acf112a8bb00815c67310580ce0fedb7e0d91597) | docs(T-2.7): make Docling a core dependency and correct the record | Promoted Docling to core and corrected planning records. |
| 2026-07-22 | [`b773947`](https://github.com/subhan-17h/CSRS/commit/b7739475ab1cd78fe91c6a7c0db0c9b9efc3f9d7) | feat(T-2.3): skip unchanged files before parsing them | Skipped unchanged files using persisted fingerprints. |
| 2026-07-22 | [`763dd60`](https://github.com/subhan-17h/CSRS/commit/763dd60eca79f60d6258d7973b8ff11f8a757634) | feat(T-2.4): populate the model selector from installed Ollama models | Populated model selection from live Ollama inventory. |
| 2026-07-22 | [`2e0173e`](https://github.com/subhan-17h/CSRS/commit/2e0173ed5a0643b421fc06a9b63d52616dae976e) | feat(T-2.5): add reload controls and a persisted document summary | Added reload controls and persisted document summaries. |
| 2026-07-22 | [`9b6f4dc`](https://github.com/subhan-17h/CSRS/commit/9b6f4dcdc0326525bb7142951a73215b60ab61ee) | feat(T-2.6): surface application settings in the sidebar | Exposed generation and retrieval settings in Streamlit. |
| 2026-07-22 | [`fc5fcb6`](https://github.com/subhan-17h/CSRS/commit/fc5fcb699479ed9e0f56dec92a92c66a8b4790ca) | fix(T-2.6): send rerank_top_n chunks to generation, not the whole pool | Limited generation context to the top chunks. |
| 2026-07-22 | [`a70abe0`](https://github.com/subhan-17h/CSRS/commit/a70abe06584dc915cc85431939688e43f3a8acfc) | phase(2): record the CSRS.md 1-6 checkpoint and close Phase 2 | Recorded verified Phase 2 completion evidence. |
| 2026-07-22 | [`32b5bfd`](https://github.com/subhan-17h/CSRS/commit/32b5bfdc9379d3c86cef2219c3e3a8dbc60312a6) | docs(T-6.1): write the submission README and the engineering narrative | Added the submission README and engineering narrative. |
| 2026-07-22 | [`5d0c2ad`](https://github.com/subhan-17h/CSRS/commit/5d0c2ad562e5d608963a0fde0f6bf080ed0f2a5f) | feat(T-7.1): add the FastAPI layer with read-only pipeline endpoints | Added lazy health, documents, and models endpoints. |
| 2026-07-22 | [`a3f674e`](https://github.com/subhan-17h/CSRS/commit/a3f674e37db747fd169c032e57af5a720f0ed4a5) | feat(T-7.2): answer questions over HTTP and serialize grounded citations | Added HTTP answers with grounded source serialization. |
| 2026-07-22 | [`a728cdb`](https://github.com/subhan-17h/CSRS/commit/a728cdb6532aa6ec5bef9fb474992532c7da25e3) | feat(T-7.3): stream answers with real retrieval stages over NDJSON | Streamed retrieval stages and answers over NDJSON. |
| 2026-07-22 | [`523223e`](https://github.com/subhan-17h/CSRS/commit/523223e45607df43d1d600841fcb67b7040bd6ab) | feat(T-7.4): reload and rebuild the index over streaming NDJSON endpoints | Added streamed reload and full rebuild endpoints. |
| 2026-07-22 | [`abda8ed`](https://github.com/subhan-17h/CSRS/commit/abda8ed0ddeee46700c01b30cd0f17e7911ed588) | feat(T-7.5): browse document chunks and serve the built frontend | Added chunk browsing and built-frontend serving. |
| 2026-07-22 | [`9d8363c`](https://github.com/subhan-17h/CSRS/commit/9d8363cf3faf952565f02ee7aafc8acb4a06c023) | feat(T-7.6): transplant the frontend onto the CSRS domain and rebrand | Added and rebranded the React TypeScript frontend. |
| 2026-07-22 | [`5fa2356`](https://github.com/subhan-17h/CSRS/commit/5fa23565ae11bbc43bbd80f4b35d23527470138f) | feat(T-7.7): render answers as markdown and citations as an expandable card | Rendered Markdown answers and expandable source cards. |
| 2026-07-23 | [`5447b3b`](https://github.com/subhan-17h/CSRS/commit/5447b3b8539be53adc2bb2b9514f3b8501296569) | feat(T-7.8): stream real tokens and live retrieval stages into the UI | Connected live tokens and retrieval stages to React. |
| 2026-07-23 | [`8d52f90`](https://github.com/subhan-17h/CSRS/commit/8d52f903053cea0c13e55dfa64b98c173c030e41) | feat(T-7.9): add the application settings sidebar with spec section 5 parity | Added the specification-parity settings sidebar. |
| 2026-07-23 | [`d3703c6`](https://github.com/subhan-17h/CSRS/commit/d3703c67f54e89fb774969f53ab7fef71379dd20) | feat(T-7.10): add a read-only Corpus Explorer for the indexed documents | Added a read-only indexed-corpus explorer. |
| 2026-07-23 | [`9f899e6`](https://github.com/subhan-17h/CSRS/commit/9f899e6391f3aece71d986119b12eff5d7d0009c) | feat(T-7.11): persist conversations in localStorage and list them in the sidebar | Persisted and listed conversations in localStorage. |
| 2026-07-23 | [`a57c0e6`](https://github.com/subhan-17h/CSRS/commit/a57c0e6eeb24606a1f0a3944c89bd28fb8ec5821) | docs(T-7.12): document both interfaces and prove the offline claim | Documented both interfaces and verified offline operation. |
| 2026-07-23 | [`462d9e9`](https://github.com/subhan-17h/CSRS/commit/462d9e9dd4238d9cb13f79e4982118cb97d9a550) | phase(7): close the web frontend phase | Recorded completion of the web frontend phase. |
| 2026-07-23 | [`b46a9fb`](https://github.com/subhan-17h/CSRS/commit/b46a9fb3191199f555a6b6e48a1a3e9523f0058f) | docs(T-7.12): record the human visual verification of both UIs | Recorded human visual verification of both interfaces. |
| 2026-07-23 | [`6479fc4`](https://github.com/subhan-17h/CSRS/commit/6479fc4f526ab5348c257076bee1e1fe7f2104f1) | fix(F-1): drop only the corrupt conversation, not the whole history | Isolated corrupt conversation deletion from valid history. |
| 2026-07-23 | [`88ec86b`](https://github.com/subhan-17h/CSRS/commit/88ec86b04cf1fe41b1895c20bd0495b7e6b46828) | docs(F-2): document stopping the processes and what it costs | Documented process shutdown and its consequences. |
| 2026-07-23 | [`3665a3d`](https://github.com/subhan-17h/CSRS/commit/3665a3dbb7797ba3d95433def4791ca28744acdb) | docs(L-6): require repo conventions to be quoted, not paraphrased | Recorded the lesson to quote repository rules exactly. |
| 2026-07-23 | [`d7b63ad`](https://github.com/subhan-17h/CSRS/commit/d7b63ad0f88458191e32c65defe343b8577459f6) | feat(T-3.1): add the evaluation golden set and its validator | Added the evaluation set and structural validator. |
| 2026-07-24 | [`9d1dbf7`](https://github.com/subhan-17h/CSRS/commit/9d1dbf7c75c65ce3ba34a0b90207dfebebcbc8e2) | docs(submission): add the instructor-facing submission document | Added the instructor-facing submission document. |
| 2026-07-24 | [`ef57d11`](https://github.com/subhan-17h/CSRS/commit/ef57d111acae29d4421e4ca9e18108b0273654e5) | docs(diagram): add the system architecture diagram | Added HTML and SVG architecture diagrams. |
| 2026-07-24 | [`f5315fe`](https://github.com/subhan-17h/CSRS/commit/f5315fe2d29527942506582cd20a8449f18c3a20) | docs(readme): add the architecture diagram and correct stale claims | Linked the diagram and corrected README claims. |
| 2026-07-24 | [`ec1b26a`](https://github.com/subhan-17h/CSRS/commit/ec1b26a16b72546f388b3ec9092e45231959dcc3) | docs(S-1..S-3): record the submission preparation work in todo.md | Recorded submission preparation tasks. |
| 2026-07-24 | [`da9ec53`](https://github.com/subhan-17h/CSRS/commit/da9ec53da82e93818b8062973e688d8a78469ba1) | feat(T-3.2a): add the retrieval metric functions and their unit tests | Implemented tested retrieval metric functions. |
| 2026-07-24 | [`b58b067`](https://github.com/subhan-17h/CSRS/commit/b58b06734205ca0525f83f1a57bd096badc2f9f3) | feat(T-3.2b): add the evaluation harness and record the Phase 3 baseline | Added the runner and recorded a retrieval baseline. |
| 2026-07-24 | [`c0d9924`](https://github.com/subhan-17h/CSRS/commit/c0d992484002f77ca562225ac2445722037827bb) | feat(T-3.3a): add the persisted BM25 sparse index | Added persisted BM25 sparse retrieval. |
| 2026-07-24 | [`5103c5e`](https://github.com/subhan-17h/CSRS/commit/5103c5ea36079a50461a35ccf172c25e7907b16c) | feat(T-3.3b): keep the BM25 index in step with the corpus | Synchronized BM25 with corpus indexing changes. |
| 2026-07-24 | [`c0cbdd2`](https://github.com/subhan-17h/CSRS/commit/c0cbdd2fefb431759084c5da6f59488e115c0920) | feat(T-3.4): add RRF fusion behind a setting, defaulting to dense | Added configurable Reciprocal Rank Fusion. |
| 2026-07-24 | [`36d5751`](https://github.com/subhan-17h/CSRS/commit/36d575150bd87dcc6febaca1ebc279bb8c3d2fc0) | feat(T-3.5): add FlashRank reranking behind a setting, disabled by default | Added optional FlashRank reranking and warming. |
| 2026-07-24 | [`7c0bcb5`](https://github.com/subhan-17h/CSRS/commit/7c0bcb5544e376a4499748e3cd6007b66b99872c) | docs(T-3.5): restore the T-1.7 context-budget note into retrieve() | Restored the retrieval context-budget note. |
| 2026-07-24 | [`f8f75b0`](https://github.com/subhan-17h/CSRS/commit/f8f75b0077bea0141797a2e5cef559253e3d8745) | feat(T-3.4): default retrieval_mode to hybrid on the re-baselined metric | Made hybrid retrieval the re-baselined default. |
| 2026-07-24 | [`a6d3241`](https://github.com/subhan-17h/CSRS/commit/a6d3241d3ccb82b32d724da434d362a42424a453) | docs(T-3.5b): re-baseline Phase 3 on rank-1 and Recall@5, fold ENGINEERING into Submission | Updated baselines and consolidated engineering documentation. |
| 2026-07-24 | [`8602d9f`](https://github.com/subhan-17h/CSRS/commit/8602d9fdb039a68353ad737bb068558dff8b5be5) | chore: move project documents into project-docs/ and leave README.md as the root doc | Moved project documents under `project-docs`. |
| 2026-07-24 | [`9600f34`](https://github.com/subhan-17h/CSRS/commit/9600f34841a047d99609dcf8c977ce25964b14f5) | feat(T-4.3a): add rewrite_query() for conversational follow-ups | Added conversation-aware follow-up rewriting. |
| 2026-07-24 | [`ff2e76f`](https://github.com/subhan-17h/CSRS/commit/ff2e76f1dbd4fd8dfbe63913192db208133e3d94) | feat(T-4.3b): search the rewritten query, generate against the original | Separated retrieval and generation question forms. |
| 2026-07-24 | [`5e86d0e`](https://github.com/subhan-17h/CSRS/commit/5e86d0e218b39219c2622629efef6564eade5970) | feat(T-4.3c): send conversation history from the web UI | Sent conversation history from React to the API. |
| 2026-07-24 | [`ac50ed2`](https://github.com/subhan-17h/CSRS/commit/ac50ed2ac7f48c21685ef7969ae9168b2fe2da47) | feat(T-8.1): serve the original document file over HTTP | Served original documents through a safe endpoint. |
| 2026-07-24 | [`11ab551`](https://github.com/subhan-17h/CSRS/commit/11ab5519c4a6c230d8e3be5d50a16e698ae7f353) | feat(T-8.2): read the source document in the Corpus tab | Added in-app source-document viewing. |
| 2026-07-24 | [`a3f4416`](https://github.com/subhan-17h/CSRS/commit/a3f441651dce7c3b9af62065914a49cb199024ee) | chore(T-8.3): add an MIT LICENSE and state the corpus boundary | Added MIT licensing and the corpus boundary. |
| 2026-07-24 | [`2d2bcc8`](https://github.com/subhan-17h/CSRS/commit/2d2bcc8ad1d888b09c1b405ee7e448c88ba19d18) | docs(T-8.4): redraw the architecture diagram for the shipped pipeline | Redrew diagrams to match the shipped pipeline. |
| 2026-07-24 | [`8bc07fc`](https://github.com/subhan-17h/CSRS/commit/8bc07fcbedaedc754c2122edac7b449d63cb6f27) | phase(8): audit against the running app and correct what the docs overclaimed | Corrected documentation through a running-app audit. |
| 2026-07-28 | [`3410a46`](https://github.com/subhan-17h/CSRS/commit/3410a46a40b2fa8b3e1b6d9bceef254c56775517) | feat(EVAL-2): add three-layer RAG evaluation | Added cosine, evidence, and Groq answer evaluation. |
| 2026-07-29 | [`99b9cb1`](https://github.com/subhan-17h/CSRS/commit/99b9cb16c38722fc7d5524da42b7e467326ec3c5) | chore(EVAL-3): require verified subtask commits | Required separate commits for verified subtasks. |
| 2026-07-29 | [`62b42d4`](https://github.com/subhan-17h/CSRS/commit/62b42d4f2eeaf7b2d69c80bc1b73cb55b29772fe) | feat(EVAL-3): add CSF-only fifty-question dataset | Added 50 CSF-only questions and coverage quotas. |
| 2026-07-29 | [`b4656f7`](https://github.com/subhan-17h/CSRS/commit/b4656f787ee5326bb6cdf457bdd649e7c3c1502a) | feat(EVAL-3): reduce shipped corpus to CSF 2.0 | Reduced the committed corpus to NIST CSF 2.0. |
| 2026-07-29 | [`965ae8b`](https://github.com/subhan-17h/CSRS/commit/965ae8b1988af142ecbad20f3d6b10b877ebd49b) | fix(EVAL-3): make direct benchmark claims atomic | Rewrote direct benchmark items as atomic claims. |
| 2026-07-29 | [`210c342`](https://github.com/subhan-17h/CSRS/commit/210c342fa4fdcde2ec89a3007477814aa5c1b861) | feat(EVAL-3): add v2 three-metric evaluator | Added cosine, BERTScore, and LLM-judge evaluation. |
| 2026-07-29 | [`21eb47c`](https://github.com/subhan-17h/CSRS/commit/21eb47c5d883f0fc0b1846e6a50615bb2bc726c7) | feat(EVAL-3): publish detailed v2 evaluation reports | Added detailed CSV and Markdown report generation. |
| 2026-07-29 | [`2d67afe`](https://github.com/subhan-17h/CSRS/commit/2d67afecb9b71b730071cea67d839e037c0e1b28) | docs(EVAL-3): describe CSF-only v2 evaluation | Updated documentation for the CSF-only evaluator. |
| 2026-07-29 | [`6737c84`](https://github.com/subhan-17h/CSRS/commit/6737c84d54f44686f35b3722d4c37399a4658781) | fix(EVAL-3): resume safely across judge quota windows | Added quota-aware retries and atomic resume replacement. |
| 2026-07-29 | [`b15c007`](https://github.com/subhan-17h/CSRS/commit/b15c0079b58b12e379592b217c6e33e3d232315a) | fix(EVAL-3): normalize detailed CSV line formatting | Normalized multiline fields in detailed CSV output. |
| 2026-07-29 | [`ef4736b`](https://github.com/subhan-17h/CSRS/commit/ef4736bd4af733da536a393daa949861c3ed7770) | feat(EVAL-3): publish final five-model evaluation | Published the complete 250-row evaluation. |
