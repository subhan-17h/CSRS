# Day Index

Every day of the CSRS internship in order, from Tuesday 21 July to Friday 21 August 2026.
The 32-day span contains **16 working days**: on each, either commits were made or a dated
artefact was produced. Nine weekdays were spent on background reading and result analysis;
seven dates are weekends.

Thirteen of the sixteen working days carry an annotated Git tag, `day-NN-YYYY-MM-DD`, placed
on that day's last commit, so the repository can be read a day at a time. Days 7, 8 and 9
produced dated artefacts rather than commits, so no commit exists to tag; they are listed
below with the files that evidence them.

```
git tag -n99 -l 'day-*'          # every day with its summary
git show day-10-2026-08-06       # what one day contains
git log day-05-2026-07-28..day-06-2026-07-29 --oneline
```

The narrative for each day is in [PROJECT_WORK_HISTORY.md](PROJECT_WORK_HISTORY.md);
the full task cards are in [tasks/todo.md](../tasks/todo.md).

## Summary

| | Count |
|---|---:|
| Working days | 16 (13 tagged, 3 evidenced by artefacts) |
| Research days | 9 |
| Weekend days | 7 |
| Total span | 32 |
| Commits | 117 |
| Lines added / removed | +46,613 / -8,579 |


### Day 1 --- Tuesday 21 July: Foundation and first working RAG

Tag: `day-01-2026-07-21`

23 commits

| Commit | Subject |
|---|---|
| [`603d1a0`](https://github.com/subhan-17h/CSRS/commit/603d1a09be49836d86ab64367f27f68f9bdf87db) | chore: initialise repository with spec and planning artefacts |
| [`d50914a`](https://github.com/subhan-17h/CSRS/commit/d50914a9881b05d0e95195d0f60e07fe130c37de) | chore(T-0.1): scaffold uv project on Python 3.12 |
| [`f883f1c`](https://github.com/subhan-17h/CSRS/commit/f883f1c4488fe69e6f7721dfb2b8daf573d2b4b7) | feat(T-0.3): add corpus fetch script and public-domain sample |
| [`5dad583`](https://github.com/subhan-17h/CSRS/commit/5dad583d62155206f28fcba91df590d782ee1608) | feat(T-0.4): add typed settings module |
| [`78a3884`](https://github.com/subhan-17h/CSRS/commit/78a3884f287050774b3eae7a0da859bfc90cd6cf) | docs(phase 0): close Phase 0 -- environment, models and corpus verified |
| [`e5c620d`](https://github.com/subhan-17h/CSRS/commit/e5c620d9e5e50918ecbfdd1bf8cffeea39988d13) | feat(T-0.4): default to llama3.2 rather than qwen2.5:1.5b |
| [`68a94ab`](https://github.com/subhan-17h/CSRS/commit/68a94abafa4bba0e92a9721fde76a56261ba5c2d) | feat(T-0.3): ship one PDF and one TXT sample, each a different standard |
| [`3d70c34`](https://github.com/subhan-17h/CSRS/commit/3d70c345402b7538eee893242c2450cfd314757f) | docs: forbid attribution trailers in commit messages |
| [`67a9f21`](https://github.com/subhan-17h/CSRS/commit/67a9f21329388ba858f0859b7f52d5ddfce5fe80) | feat(T-1.1): add the data models every module exchanges |
| [`bba6ec5`](https://github.com/subhan-17h/CSRS/commit/bba6ec5eebdcf6f93470fb4733f6be49d101632c) | docs: require a watcher on every Codex task |
| [`436e267`](https://github.com/subhan-17h/CSRS/commit/436e2673b61e78b030658915232ffba7ffd74dd5) | feat(T-1.2): add DocumentParser protocol, TXT loader and registry |
| [`09085e2`](https://github.com/subhan-17h/CSRS/commit/09085e2133908930be148510f7bd1d7d7f53a95e) | docs: make Codex keep tasks/todo.md current, and pin its constraints |
| [`5e0ab5f`](https://github.com/subhan-17h/CSRS/commit/5e0ab5fa5dec28dcc15ac54493007d4ed7956648) | feat(T-1.3): add naive recursive chunker with real text overlap |
| [`647b16e`](https://github.com/subhan-17h/CSRS/commit/647b16e02c12a5157ddf07f06d4590eeeeeb3468) | docs: identify the Codex job before attaching a watcher |
| [`ce02e1f`](https://github.com/subhan-17h/CSRS/commit/ce02e1fcc4a490e7d324e9e9097a851a4cbccf9b) | feat(T-1.4): embed via Ollama with the mandatory nomic task prefixes |
| [`16ee54a`](https://github.com/subhan-17h/CSRS/commit/16ee54ab6955925b1da16a3787a05bc56588306e) | feat(T-1.5): persist chunks in Chroma with cosine space and our own vectors |
| [`72a1843`](https://github.com/subhan-17h/CSRS/commit/72a1843a4e3d6a18c9e60e17175bf3244c293eba) | feat(T-1.6): generate grounded answers with a literal refusal string |
| [`2a5f0a6`](https://github.com/subhan-17h/CSRS/commit/2a5f0a609c43f86347c9a12e47c20b2a464f93a2) | feat(T-1.7): add the Pipeline facade the UI and eval harness both drive |
| [`e4e32a1`](https://github.com/subhan-17h/CSRS/commit/e4e32a1bd63c2bc19316f6635e7b9634af9ca803) | feat(T-1.8): add the minimal Streamlit app that closes the loop |
| [`fd56a5f`](https://github.com/subhan-17h/CSRS/commit/fd56a5fb2e15eb319ba34f32a91220c8a626017b) | docs(phase 1): close Phase 1 with the checkpoint findings |
| [`f861318`](https://github.com/subhan-17h/CSRS/commit/f8613180a9ac6114ac8fd5d015a723236fe1b437) | feat(T-2.1): parse PDFs into page-preserving documents |
| [`061ef52`](https://github.com/subhan-17h/CSRS/commit/061ef5258c266c25f6915f05050e6a880394d0b0) | fix(T-2.1): strip running boilerplate the full corpus actually has |
| [`85a7735`](https://github.com/subhan-17h/CSRS/commit/85a773513638d7bff1cc1005f76728acc2d19f66) | feat(T-2.2): split on control boundaries and embed hierarchy breadcrumbs |

### Day 2 --- Wednesday 22 July: Production ingestion and web application

Tag: `day-02-2026-07-22`

18 commits

| Commit | Subject |
|---|---|
| [`0e45c98`](https://github.com/subhan-17h/CSRS/commit/0e45c98aa0027c3c3131d271341e8593798d3e42) | feat(T-2.7): add Docling as the default PDF parser behind config |
| [`fee4fe7`](https://github.com/subhan-17h/CSRS/commit/fee4fe7aaabd7e8fa1891d322cf68a8108a08fc1) | feat(T-2.7): drive chunk hierarchy from Docling's Markdown headings |
| [`cb16167`](https://github.com/subhan-17h/CSRS/commit/cb1616731ff48f48dd81fc0f008f8804df0e9a72) | feat(T-2.7): add warm_models.py so offline operation is a setup step |
| [`acf112a`](https://github.com/subhan-17h/CSRS/commit/acf112a8bb00815c67310580ce0fedb7e0d91597) | docs(T-2.7): make Docling a core dependency and correct the record |
| [`b773947`](https://github.com/subhan-17h/CSRS/commit/b7739475ab1cd78fe91c6a7c0db0c9b9efc3f9d7) | feat(T-2.3): skip unchanged files before parsing them |
| [`763dd60`](https://github.com/subhan-17h/CSRS/commit/763dd60eca79f60d6258d7973b8ff11f8a757634) | feat(T-2.4): populate the model selector from installed Ollama models |
| [`2e0173e`](https://github.com/subhan-17h/CSRS/commit/2e0173ed5a0643b421fc06a9b63d52616dae976e) | feat(T-2.5): add reload controls and a persisted document summary |
| [`9b6f4dc`](https://github.com/subhan-17h/CSRS/commit/9b6f4dcdc0326525bb7142951a73215b60ab61ee) | feat(T-2.6): surface application settings in the sidebar |
| [`fc5fcb6`](https://github.com/subhan-17h/CSRS/commit/fc5fcb699479ed9e0f56dec92a92c66a8b4790ca) | fix(T-2.6): send rerank_top_n chunks to generation, not the whole pool |
| [`a70abe0`](https://github.com/subhan-17h/CSRS/commit/a70abe06584dc915cc85431939688e43f3a8acfc) | phase(2): record the CSRS.md 1-6 checkpoint and close Phase 2 |
| [`32b5bfd`](https://github.com/subhan-17h/CSRS/commit/32b5bfdc9379d3c86cef2219c3e3a8dbc60312a6) | docs(T-6.1): write the submission README and the engineering narrative |
| [`5d0c2ad`](https://github.com/subhan-17h/CSRS/commit/5d0c2ad562e5d608963a0fde0f6bf080ed0f2a5f) | feat(T-7.1): add the FastAPI layer with read-only pipeline endpoints |
| [`a3f674e`](https://github.com/subhan-17h/CSRS/commit/a3f674e37db747fd169c032e57af5a720f0ed4a5) | feat(T-7.2): answer questions over HTTP and serialize grounded citations |
| [`a728cdb`](https://github.com/subhan-17h/CSRS/commit/a728cdb6532aa6ec5bef9fb474992532c7da25e3) | feat(T-7.3): stream answers with real retrieval stages over NDJSON |
| [`523223e`](https://github.com/subhan-17h/CSRS/commit/523223e45607df43d1d600841fcb67b7040bd6ab) | feat(T-7.4): reload and rebuild the index over streaming NDJSON endpoints |
| [`abda8ed`](https://github.com/subhan-17h/CSRS/commit/abda8ed0ddeee46700c01b30cd0f17e7911ed588) | feat(T-7.5): browse document chunks and serve the built frontend |
| [`9d8363c`](https://github.com/subhan-17h/CSRS/commit/9d8363cf3faf952565f02ee7aafc8acb4a06c023) | feat(T-7.6): transplant the frontend onto the CSRS domain and rebrand |
| [`5fa2356`](https://github.com/subhan-17h/CSRS/commit/5fa23565ae11bbc43bbd80f4b35d23527470138f) | feat(T-7.7): render answers as markdown and citations as an expandable card |

### Day 3 --- Thursday 23 July: Frontend completion and hardening

Tag: `day-03-2026-07-23`

11 commits

| Commit | Subject |
|---|---|
| [`5447b3b`](https://github.com/subhan-17h/CSRS/commit/5447b3b8539be53adc2bb2b9514f3b8501296569) | feat(T-7.8): stream real tokens and live retrieval stages into the UI |
| [`8d52f90`](https://github.com/subhan-17h/CSRS/commit/8d52f903053cea0c13e55dfa64b98c173c030e41) | feat(T-7.9): add the application settings sidebar with spec section 5 parity |
| [`d3703c6`](https://github.com/subhan-17h/CSRS/commit/d3703c67f54e89fb774969f53ab7fef71379dd20) | feat(T-7.10): add a read-only Corpus Explorer for the indexed documents |
| [`9f899e6`](https://github.com/subhan-17h/CSRS/commit/9f899e6391f3aece71d986119b12eff5d7d0009c) | feat(T-7.11): persist conversations in localStorage and list them in the sidebar |
| [`a57c0e6`](https://github.com/subhan-17h/CSRS/commit/a57c0e6eeb24606a1f0a3944c89bd28fb8ec5821) | docs(T-7.12): document both interfaces and prove the offline claim |
| [`462d9e9`](https://github.com/subhan-17h/CSRS/commit/462d9e9dd4238d9cb13f79e4982118cb97d9a550) | phase(7): close the web frontend phase |
| [`b46a9fb`](https://github.com/subhan-17h/CSRS/commit/b46a9fb3191199f555a6b6e48a1a3e9523f0058f) | docs(T-7.12): record the human visual verification of both UIs |
| [`6479fc4`](https://github.com/subhan-17h/CSRS/commit/6479fc4f526ab5348c257076bee1e1fe7f2104f1) | fix(F-1): drop only the corrupt conversation, not the whole history |
| [`88ec86b`](https://github.com/subhan-17h/CSRS/commit/88ec86b04cf1fe41b1895c20bd0495b7e6b46828) | docs(F-2): document stopping the processes and what it costs |
| [`3665a3d`](https://github.com/subhan-17h/CSRS/commit/3665a3dbb7797ba3d95433def4791ca28744acdb) | docs(L-6): require repo conventions to be quoted, not paraphrased |
| [`d7b63ad`](https://github.com/subhan-17h/CSRS/commit/d7b63ad0f88458191e32c65defe343b8577459f6) | feat(T-3.1): add the evaluation golden set and its validator |

### Day 4 --- Friday 24 July: Retrieval quality, conversation context, and submission

Tag: `day-04-2026-07-24`

22 commits

| Commit | Subject |
|---|---|
| [`9d1dbf7`](https://github.com/subhan-17h/CSRS/commit/9d1dbf7c75c65ce3ba34a0b90207dfebebcbc8e2) | docs(submission): add the instructor-facing submission document |
| [`ef57d11`](https://github.com/subhan-17h/CSRS/commit/ef57d111acae29d4421e4ca9e18108b0273654e5) | docs(diagram): add the system architecture diagram |
| [`f5315fe`](https://github.com/subhan-17h/CSRS/commit/f5315fe2d29527942506582cd20a8449f18c3a20) | docs(readme): add the architecture diagram and correct stale claims |
| [`ec1b26a`](https://github.com/subhan-17h/CSRS/commit/ec1b26a16b72546f388b3ec9092e45231959dcc3) | docs(S-1..S-3): record the submission preparation work in todo.md |
| [`da9ec53`](https://github.com/subhan-17h/CSRS/commit/da9ec53da82e93818b8062973e688d8a78469ba1) | feat(T-3.2a): add the retrieval metric functions and their unit tests |
| [`b58b067`](https://github.com/subhan-17h/CSRS/commit/b58b06734205ca0525f83f1a57bd096badc2f9f3) | feat(T-3.2b): add the evaluation harness and record the Phase 3 baseline |
| [`c0d9924`](https://github.com/subhan-17h/CSRS/commit/c0d992484002f77ca562225ac2445722037827bb) | feat(T-3.3a): add the persisted BM25 sparse index |
| [`5103c5e`](https://github.com/subhan-17h/CSRS/commit/5103c5ea36079a50461a35ccf172c25e7907b16c) | feat(T-3.3b): keep the BM25 index in step with the corpus |
| [`c0cbdd2`](https://github.com/subhan-17h/CSRS/commit/c0cbdd2fefb431759084c5da6f59488e115c0920) | feat(T-3.4): add RRF fusion behind a setting, defaulting to dense |
| [`36d5751`](https://github.com/subhan-17h/CSRS/commit/36d575150bd87dcc6febaca1ebc279bb8c3d2fc0) | feat(T-3.5): add FlashRank reranking behind a setting, disabled by default |
| [`7c0bcb5`](https://github.com/subhan-17h/CSRS/commit/7c0bcb5544e376a4499748e3cd6007b66b99872c) | docs(T-3.5): restore the T-1.7 context-budget note into retrieve() |
| [`f8f75b0`](https://github.com/subhan-17h/CSRS/commit/f8f75b0077bea0141797a2e5cef559253e3d8745) | feat(T-3.4): default retrieval_mode to hybrid on the re-baselined metric |
| [`a6d3241`](https://github.com/subhan-17h/CSRS/commit/a6d3241d3ccb82b32d724da434d362a42424a453) | docs(T-3.5b): re-baseline Phase 3 on rank-1 and Recall@5, fold ENGINEERING into Submission |
| [`8602d9f`](https://github.com/subhan-17h/CSRS/commit/8602d9fdb039a68353ad737bb068558dff8b5be5) | chore: move project documents into project-docs/ and leave README.md as the root doc |
| [`9600f34`](https://github.com/subhan-17h/CSRS/commit/9600f34841a047d99609dcf8c977ce25964b14f5) | feat(T-4.3a): add rewrite_query() for conversational follow-ups |
| [`ff2e76f`](https://github.com/subhan-17h/CSRS/commit/ff2e76f1dbd4fd8dfbe63913192db208133e3d94) | feat(T-4.3b): search the rewritten query, generate against the original |
| [`5e86d0e`](https://github.com/subhan-17h/CSRS/commit/5e86d0e218b39219c2622629efef6564eade5970) | feat(T-4.3c): send conversation history from the web UI |
| [`ac50ed2`](https://github.com/subhan-17h/CSRS/commit/ac50ed2ac7f48c21685ef7969ae9168b2fe2da47) | feat(T-8.1): serve the original document file over HTTP |
| [`11ab551`](https://github.com/subhan-17h/CSRS/commit/11ab5519c4a6c230d8e3be5d50a16e698ae7f353) | feat(T-8.2): read the source document in the Corpus tab |
| [`a3f4416`](https://github.com/subhan-17h/CSRS/commit/a3f441651dce7c3b9af62065914a49cb199024ee) | chore(T-8.3): add an MIT LICENSE and state the corpus boundary |
| [`2d2bcc8`](https://github.com/subhan-17h/CSRS/commit/2d2bcc8ad1d888b09c1b405ee7e448c88ba19d18) | docs(T-8.4): redraw the architecture diagram for the shipped pipeline |
| [`8bc07fc`](https://github.com/subhan-17h/CSRS/commit/8bc07fcbedaedc754c2122edac7b449d63cb6f27) | phase(8): audit against the running app and correct what the docs overclaimed |

### Saturday 25 July --- weekend


### Sunday 26 July --- weekend


### Research day --- Monday 27 July: Evaluation method and retrieval-improvement reading

No commits. Anchored to: [RESEARCH.md](RESEARCH.md) §2 fusion, §3 reranking, §7 evaluation, §4 architectures declined


### Day 5 --- Tuesday 28 July: Evidence-grounded answer evaluation

Tag: `day-05-2026-07-28`

1 commits

| Commit | Subject |
|---|---|
| [`3410a46`](https://github.com/subhan-17h/CSRS/commit/3410a46a40b2fa8b3e1b6d9bceef254c56775517) | feat(EVAL-2): add three-layer RAG evaluation |

### Day 6 --- Wednesday 29 July: CSF-only five-model evaluation

Tag: `day-06-2026-07-29`

13 commits

| Commit | Subject |
|---|---|
| [`99b9cb1`](https://github.com/subhan-17h/CSRS/commit/99b9cb16c38722fc7d5524da42b7e467326ec3c5) | chore(EVAL-3): require verified subtask commits |
| [`62b42d4`](https://github.com/subhan-17h/CSRS/commit/62b42d4f2eeaf7b2d69c80bc1b73cb55b29772fe) | feat(EVAL-3): add CSF-only fifty-question dataset |
| [`b4656f7`](https://github.com/subhan-17h/CSRS/commit/b4656f787ee5326bb6cdf457bdd649e7c3c1502a) | feat(EVAL-3): reduce shipped corpus to CSF 2.0 |
| [`965ae8b`](https://github.com/subhan-17h/CSRS/commit/965ae8b1988af142ecbad20f3d6b10b877ebd49b) | fix(EVAL-3): make direct benchmark claims atomic |
| [`210c342`](https://github.com/subhan-17h/CSRS/commit/210c342fa4fdcde2ec89a3007477814aa5c1b861) | feat(EVAL-3): add v2 three-metric evaluator |
| [`21eb47c`](https://github.com/subhan-17h/CSRS/commit/21eb47c5d883f0fc0b1846e6a50615bb2bc726c7) | feat(EVAL-3): publish detailed v2 evaluation reports |
| [`2d67afe`](https://github.com/subhan-17h/CSRS/commit/2d67afecb9b71b730071cea67d839e037c0e1b28) | docs(EVAL-3): describe CSF-only v2 evaluation |
| [`6737c84`](https://github.com/subhan-17h/CSRS/commit/6737c84d54f44686f35b3722d4c37399a4658781) | fix(EVAL-3): resume safely across judge quota windows |
| [`b15c007`](https://github.com/subhan-17h/CSRS/commit/b15c0079b58b12e379592b217c6e33e3d232315a) | fix(EVAL-3): normalize detailed CSV line formatting |
| [`ef4736b`](https://github.com/subhan-17h/CSRS/commit/ef4736bd4af733da536a393daa949861c3ed7770) | feat(EVAL-3): publish final five-model evaluation |
| [`a9e3312`](https://github.com/subhan-17h/CSRS/commit/a9e33124c15db5a74c10bc1f9086b0fe6915df28) | docs(HIST-1): establish verified project chronology |
| [`42f36bc`](https://github.com/subhan-17h/CSRS/commit/42f36bc4f8e04bf18b5d0ee2f3c7139d6b133033) | docs(HIST-1): audit implementation and evaluation outcome |
| [`f61d807`](https://github.com/subhan-17h/CSRS/commit/f61d8078a661d7c31455dc03500b0e7b790f3c43) | docs(HIST-1): close verified project work record |

### Day 7 --- Thursday 30 July: Snort alert dataset preparation

No tag: this day produced artefacts rather than commits.

No commits. Evidence: `enriched_snort_alerts.json` (2.7 MB) -- the 50-alert dataset


### Day 8 --- Friday 31 July: Rule-documentation scraping session

No tag: this day produced artefacts rather than commits.

No commits. Evidence: 16 files under `.playwright-mcp/` -- console logs, 9 page snapshots, 4 screenshots


### Saturday 1 August --- weekend


### Sunday 2 August --- weekend


### Day 9 --- Monday 3 August: The alert-severity criteria

No tag: this day produced artefacts rather than commits.

No commits. Evidence: `cretria.md` -- the nine-criterion severity rubric


### Research day --- Tuesday 4 August: Severity semantics and task design

No commits. Anchored to: `cretria.md` (Day 9) -- ground truth and prompt design


### Research day --- Wednesday 5 August: Severity semantics and task design

No commits. Anchored to: `cretria.md` (Day 9) -- sampling and the visible-priority problem


### Day 10 --- Thursday 6 August: Alert-ranking RAG foundation

Tag: `day-10-2026-08-06`

5 commits

| Commit | Subject |
|---|---|
| [`84fab52`](https://github.com/subhan-17h/CSRS/commit/84fab5206303850884cee689c5b146639771ac3f) | chore(ALERT-RAG): ignore experiment standards PDFs |
| [`c670fd5`](https://github.com/subhan-17h/CSRS/commit/c670fd591d4f7f98ed1d6e2bfbd0181c4eaf3c9e) | feat(ALERT-RAG): fetch NIST SP 800-53r5 alongside CSF 2.0 |
| [`16963f0`](https://github.com/subhan-17h/CSRS/commit/16963f098cc1b016785295c7e0bd951ef4b717ff) | fix(ALERT-RAG): verify_manifest tolerates corpus supersets |
| [`625a673`](https://github.com/subhan-17h/CSRS/commit/625a67304da9049dc9259ee6e221d0e530163bee) | feat(ALERT-RAG): RAG-grounded alert severity ranking runner |
| [`905eb5e`](https://github.com/subhan-17h/CSRS/commit/905eb5e044681ec09163462468096821139f8b24) | feat(ALERT-RAG): alert RAG report builder |

### Research day --- Friday 7 August: Judge design and the mismatch rule

No commits. Anchored to: [RESEARCH.md](RESEARCH.md) §7; the anchor mapping


### Saturday 8 August --- weekend


### Sunday 9 August --- weekend


### Day 11 --- Monday 10 August: Mismatch and judge passes

Tag: `day-11-2026-08-10`

4 commits

| Commit | Subject |
|---|---|
| [`1d47a97`](https://github.com/subhan-17h/CSRS/commit/1d47a977268bf7d911978f3c5d9b9f3e846f88d6) | feat(ALERT-RAG): shared Snort-priority anchor + mismatch rule |
| [`b17b59c`](https://github.com/subhan-17h/CSRS/commit/b17b59cd7a7e247ca5352f17e4b144a8e95b7d94) | feat(ALERT-RAG): mismatch justification pass |
| [`d71815e`](https://github.com/subhan-17h/CSRS/commit/d71815e35115f26b2ec1cb12ffd8b5b130a6fef1) | feat(ALERT-RAG): Groq GPT-OSS severity judge pass |
| [`5f44b8e`](https://github.com/subhan-17h/CSRS/commit/5f44b8eb3b69965d870ba8b69c468d8092b3910e) | feat(ALERT-RAG): merge mismatch and judge verdicts into report deliverables |

### Day 12 --- Tuesday 11 August: Groq migration

Tag: `day-12-2026-08-11`

6 commits

| Commit | Subject |
|---|---|
| [`407e8b8`](https://github.com/subhan-17h/CSRS/commit/407e8b8460424b4f5a3f0c24426d639bfd330b71) | feat(ALERT-GROQ-1): shared Groq transport and rate limiter for alert experiments |
| [`61cad71`](https://github.com/subhan-17h/CSRS/commit/61cad715a04fa163f3c2a84d8c94f00c556e6ba5) | feat(ALERT-GROQ-2): run the alert ranking runner on Groq gpt-oss-120b |
| [`1e78f23`](https://github.com/subhan-17h/CSRS/commit/1e78f2364169db5c76543592fbac8460beb16bc6) | feat(ALERT-GROQ-3): justify mismatches with Groq gpt-oss-120b |
| [`5bccc21`](https://github.com/subhan-17h/CSRS/commit/5bccc2107859edb5825c112205578520da777070) | feat(ALERT-GROQ-4): rate-limit and quota-stop the Groq judge pass |
| [`77627a8`](https://github.com/subhan-17h/CSRS/commit/77627a8942ddf69bb17f43dd4684172f1048d977) | feat(ALERT-GROQ-5): derive report models from the run snapshot |
| [`b1b3d6b`](https://github.com/subhan-17h/CSRS/commit/b1b3d6b890cf7f9c64ec3185643cf9bd1d0010a7) | fix(ALERT-GROQ): pass reasoning_effort=low so gpt-oss-120b emits content |

### Day 13 --- Wednesday 12 August: v1 production run

Tag: `day-13-2026-08-12`

1 commits

| Commit | Subject |
|---|---|
| [`bb84dbc`](https://github.com/subhan-17h/CSRS/commit/bb84dbc0d0d2afa1f680228a8ee556b89235ce3f) | chore(ALERT-GROQ-6): close the Groq migration with the production run |

### Day 14 --- Thursday 13 August: v2 - split models, clean JSON, full-ruleset SID matching

Tag: `day-14-2026-08-13`

8 commits

| Commit | Subject |
|---|---|
| [`918f661`](https://github.com/subhan-17h/CSRS/commit/918f661a25c4457df42525fc9619d7a28123794d) | feat(ALERT-GROQ-7): gate reasoning request options by model support |
| [`93bd0b0`](https://github.com/subhan-17h/CSRS/commit/93bd0b01a9a25f4284356c844ce897c53275cfc8) | feat(ALERT-GROQ-7): ranker v2 - JSON contract, model_rank, alert-only record, sid matching |
| [`dcd0741`](https://github.com/subhan-17h/CSRS/commit/dcd074152da98b04f5ac436552488a2f55f9bb1e) | feat(ALERT-GROQ-7): judge v2 - qwen judge, json_object contract, model_rank |
| [`694c259`](https://github.com/subhan-17h/CSRS/commit/694c259743be8384bcf066a5bdbd8ed1ee98421f) | feat(ALERT-GROQ-7): fetch Snort rule documentation pages into the corpus |
| [`a82adea`](https://github.com/subhan-17h/CSRS/commit/a82adeaaa3654e5e30cf2f1106d5fa45b6557569) | feat(ALERT-GROQ-7): flat v2 deliverable schema in the report builder |
| [`7f81b49`](https://github.com/subhan-17h/CSRS/commit/7f81b49d9e87d65fab632f263a90a0c8c4dbcf21) | chore(ALERT-GROQ-7): retire the mismatch justify pass and ignore fetched Snort docs |
| [`9fb1d75`](https://github.com/subhan-17h/CSRS/commit/9fb1d75a9a56848a0e82ca921ec705c504d1684b) | feat(ALERT-GROQ-7): ingest the full Snort community ruleset as per-rule corpus docs |
| [`3725ade`](https://github.com/subhan-17h/CSRS/commit/3725adede4f54d3ab2d7fbbd00ad23bbaf8a42d7) | chore(ALERT-GROQ-7): close v2 with the production run on the full ruleset corpus |

### Research day --- Friday 14 August: v2 result analysis

No commits. Anchored to: [tasks/todo.md](../tasks/todo.md) ALERT-GROQ-7 review section


### Day 15 --- Saturday 15 August: Work record and evaluation artifacts

Tag: `day-15-2026-08-15`

3 commits

| Commit | Subject |
|---|---|
| [`4b5154f`](https://github.com/subhan-17h/CSRS/commit/4b5154f565599e1a3cfd835cc88e1f46e9466518) | docs(HIST-2): complete the verified work history through alert-ranking v2 |
| [`eb8db0a`](https://github.com/subhan-17h/CSRS/commit/eb8db0a2f53eb5aee50a111e69a12ea95d3479c8) | chore(eval): commit the evaluation summary and report artifacts |
| [`9e3b0df`](https://github.com/subhan-17h/CSRS/commit/9e3b0df87dfcf688fa15c26ea36750ac8c11b5a5) | docs(PDF-1): add the LaTeX internship work record and its figure pipeline |

### Sunday 16 August --- weekend


### Research day --- Monday 17 August: Corpus quality investigation

No commits. Anchored to: [tasks/todo.md](../tasks/todo.md); rule-doc bundle preparation


### Research day --- Tuesday 18 August: Corpus quality investigation

No commits. Anchored to: [tasks/todo.md](../tasks/todo.md); rule-doc bundle preparation


### Research day --- Wednesday 19 August: Corpus quality investigation

No commits. Anchored to: [tasks/todo.md](../tasks/todo.md); rule-doc bundle preparation


### Research day --- Thursday 20 August: Corpus quality investigation

No commits. Anchored to: [tasks/todo.md](../tasks/todo.md); rule-doc bundle preparation


### Day 16 --- Friday 21 August: v3 - the detailed rule corpus

Tag: `day-16-2026-08-21`

2 commits

| Commit | Subject |
|---|---|
| [`57a2a8f`](https://github.com/subhan-17h/CSRS/commit/57a2a8fdca6615d31c972c0cf8fc6a5e17abcfb1) | feat(ALERT-RAG-8): render the RAG corpus from the detailed rule documentation |
| [`7272e68`](https://github.com/subhan-17h/CSRS/commit/7272e6895c34a0521fb4b737a4e7482b87b4cf1c) | phase(ALERT-RAG-8): close the detailed-corpus phase with the measured outcome |
