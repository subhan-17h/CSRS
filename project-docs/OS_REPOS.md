# OS_REPOS.md — Open Source Landscape for CSRS

**Cybersecurity Standards RAG System** · surveyed 2026-07-21

A working reference, not a link dump. Every entry answers one question: **what specifically do we take from it?** The evidence behind the choices is in [RESEARCH.md](RESEARCH.md); the build order is in [ROADMAP.md](ROADMAP.md).

All star counts and URLs were fetched and verified on 2026-07-21. Several figures from the initial research sweep were stale by 2–5× and have been corrected.

---

## ⚠ First: the offline hazard table

Our hardest constraint is *"runs entirely offline after the required dependencies and models are installed."* A library that downloads weights on first use silently breaks that promise — the app works on your machine and fails on the grader's.

| Component | Downloads at runtime? | How we handle it |
|---|---|---|
| `pypdf`, `pdfplumber` | **No** — pure Python | Selectable fallback via `CSRS_PDF_PARSER=pypdf`. |
| `bm25s` | **No** — numpy only | Safe. |
| `chromadb` | **No** (with our own embeddings) | Safe. **Must not** use Chroma's default embedding function, which would fetch ONNX MiniLM. |
| `ollama` (client) | No | Models pulled explicitly via `ollama pull` — a download the spec already sanctions. |
| **`flashrank`** | **Yes** — ONNX weights on first use | ~34 MB, one-time. `scripts/warm_models.py` + documented setup step. |
| **`docling`** | **Yes** — layout/table models, ~1.3 GB | Default parser. `scripts/warm_models.py` + pinned `artifacts_path`; no runtime fetches after setup. |
| `sentence-transformers` | Yes — HF models + torch | **Not used.** |
| `tiktoken` | Yes — BPE vocab on first use | **Not used** — avoided by counting tokens heuristically. |

**The rule this produces:** anything that downloads weights needs an explicit warm-up script and documented setup step, or does not ship. Docling and FlashRank are both warmed before offline use; Docling also pins its local `artifacts_path`.

---

## 1. End-to-end local RAG applications

Reference implementations. We are not forking any of them — the spec wants our own modular pipeline — but they are the fastest way to see how these pieces fit in production.

| Repo | ★ | License | Take from it |
|---|---|---|---|
| [zylon-ai/private-gpt](https://github.com/zylon-ai/private-gpt) | 57.3k | Apache-2.0 | The original offline-RAG reference. Read its **ingestion abstraction** — how it keeps parsing, chunking, and embedding swappable behind interfaces. That layering is what "modular and maintainable" means concretely. |
| [infiniflow/ragflow](https://github.com/infiniflow/ragflow) | 85.5k | Apache-2.0 | **Chunking templates per document type** and **grounded citations**. RAGFlow's core thesis — that deep document understanding beats clever retrieval — is exactly our conclusion for standards PDFs. |
| [onyx-dot-app/onyx](https://github.com/onyx-dot-app/onyx) | 31.1k | MIT | Production **hybrid BM25 + dense** retrieval and genuine air-gapped deployment. The most credible "runs without internet" implementation here. *(Formerly Danswer; old URLs redirect.)* |
| [Cinnamon/kotaemon](https://github.com/Cinnamon/kotaemon) | 25.6k | Apache-2.0 | **The closest analogue to what we are building.** Hybrid retrieval + reranking + citation tracking with in-browser source viewing, Ollama-capable. Read its citation UI before building ours. |
| [SciPhi-AI/R2R](https://github.com/SciPhi-AI/R2R) | ~8k | Apache-2.0 | Clean retrieval-pipeline abstractions and a `local_ollama` config mode. |
| [truefoundry/cognita](https://github.com/truefoundry/cognita) | ~8k | MIT | Modular parser/embedder/retriever component boundaries — a good sanity check on our module layout. |

**Read first: `kotaemon`.** Same problem, same constraints, further along.

---

## 2. RAG frameworks — surveyed, then declined

We hand-roll the pipeline ([RESEARCH.md](RESEARCH.md), decision locked). These remain the best source of *patterns*.

| Repo | ★ | Why we're not using it | What we still borrow |
|---|---|---|---|
| [run-llama/llama-index](https://github.com/run-llama/llama-index) | ~65k | Heavy dep tree; hides the mechanics we want to learn | **Node-parser design** and the small-to-big retriever pattern — read `node_parser/` before writing our chunker |
| [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | ~18k | Same | Cleanest component/pipeline boundaries of any framework |
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | ~90k+ | Same, plus 1.x churn | `RecursiveCharacterTextSplitter`'s separator-cascade algorithm — a ~100-line idea worth reimplementing deliberately |
| [neuml/txtai](https://github.com/neuml/txtai) | ~7k | Would replace decisions we want to make ourselves | Compact all-in-one sparse+dense design |

**Why decline them.** A framework earns its weight by solving problems you have. Ours are: one embedding model, one vector store, one inference backend, and roughly 800 lines of pipeline. A framework here mostly adds indirection between you and the concepts — and a grader reading `retrieval.py` learns more from 40 explicit lines than from a `VectorIndexRetriever` construction.

---

## 3. PDF parsing

The hardest technical problem in this project. NIST SP 800-53 Rev 5 is 400+ pages of nested control tables; naive extraction produces text soup.

| Repo | License | Runtime downloads | Verdict |
|---|---|---|---|
| [py-pdf/pypdf](https://github.com/py-pdf/pypdf) · v6.14.2 | BSD-3 | **None** | **FALLBACK** — pure Python text extraction, selectable with `CSRS_PDF_PARSER=pypdf` |
| [jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) · v0.11.10 | MIT | **None** | **FALLBACK (tables)** — visual line-based table extraction with page provenance, used by the selectable pypdf path |
| [docling-project/docling](https://github.com/docling-project/docling) · v2.114.0 | MIT | **None after warm-up** | **DEFAULT** — layout-aware parsing and TableFormer table extraction |
| [pymupdf/pymupdf4llm](https://github.com/pymupdf/pymupdf4llm) | **AGPL-3.0** | None | **REJECTED** — technically excellent, but AGPL on a submitted deliverable is a real licensing hazard |
| [datalab-to/marker](https://github.com/datalab-to/marker) | GPL-3.0 | Yes (~2–4 GB) | **REJECTED** — licence + weight |
| [opendatalab/MinerU](https://github.com/opendatalab/MinerU) | Apache-2.0 | Yes | **REJECTED** — heavy; multi-format support we don't need |
| [Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) | Apache-2.0 | With extras | **REJECTED** — offline behaviour depends on which extras are installed; too easy to get wrong |

**The AGPL point is worth internalising.** PyMuPDF is the fastest and arguably best of these. It is dual-licensed AGPL-3.0 / commercial, and AGPL's network-use clause makes it a poor default in a web app you might distribute. Being able to explain *why you didn't use the fastest library* is a better signal than having used it.

### Docling, done safely
The current default is configured for air-gapped operation:
- `settings.docling_artifacts_path` pins `artifacts_path` to the local model cache, disabling runtime fetches
- `scripts/warm_models.py` fetches the Docling layout and TableFormer weights during setup
- OCR models are deliberately excluded because the parser uses `do_ocr=False` on this digital-native corpus
- [Offline discussion #2724](https://github.com/docling-project/docling/discussions/2724) · [Advanced options](https://docling-project.github.io/docling/usage/advanced_options/)

On SP 800-53 (492 pages), Docling ran at 1.99 pages/s (246.8 s) and classified 1937 page-header/page-footer items as furniture, with 0 items lacking page provenance. The previous pypdf path needed four rounds of hand-tuned heuristics to strip the same running headers and footers.

---

## 4. Chunking

| Repo | ★ | License | Verdict |
|---|---|---|---|
| [feyninc/chonkie](https://github.com/feyninc/chonkie) · v1.7.0 | 4.5k | MIT | **REFERENCE** — 12 chunker types, 505 KB wheel. Read `RecursiveChunker` and `TableChunker`. We implement our own because control-boundary splitting is domain logic no library ships |
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) (`text-splitters`) | — | MIT | **REFERENCE** — the separator-cascade algorithm, worth reading once |
| [aurelio-labs/semantic-chunkers](https://github.com/aurelio-labs/semantic-chunkers) | ~2k | MIT | **SKIP** — see [RESEARCH.md §1](RESEARCH.md#semantic-chunking); the technique itself doesn't hold up |

**Why we write our own chunker.** Generic splitters optimise for "don't break mid-sentence." We need "don't break mid-*control*, and remember which control this is." That requires knowing what `AC-2` and `ID.AM-01` look like — domain knowledge, and about 80 lines of regex and state.

---

## 5. Local vector stores

| Repo | ★ | License | Hybrid? | Verdict |
|---|---|---|---|---|
| [chroma-core/chroma](https://github.com/chroma-core/chroma) · v1.5.9 | ~15k | Apache-2.0 | No | **CHOSEN** — embedded, persistent, metadata filtering, upsert/delete, instantly recognisable to a reviewer |
| [lancedb/lancedb](https://github.com/lancedb/lancedb) · v0.34.0 | ~4k | Apache-2.0 | Partial | Runner-up — lighter and faster, less familiar |
| [qdrant/qdrant](https://github.com/qdrant/qdrant) · client v1.18.0 | ~21k | Apache-2.0 | Yes (server) | Best native hybrid, but that lives server-side; local mode doesn't give us the win |
| [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec) | ~2.5k | MIT/Apache | Via FTS5 | Most elegant (one file, vectors + BM25). Still pre-1.0 — too much risk for a graded build |
| [facebookresearch/faiss](https://github.com/facebookresearch/faiss) | ~31k | MIT | No | No persistence, no metadata — we'd rebuild half of Chroma |

**Two Chroma-specific traps**, both silent:
1. It defaults to **L2 distance**; `nomic-embed-text` is normalised and wants **cosine**. Set `hnsw:space` at collection creation.
2. Its default embedding function **downloads an ONNX MiniLM**. We always pass our own vectors — otherwise the app breaks offline *and* silently stops using the mandated model.

Known issue: HNSW index corruption on hard process exit. Mitigation is in the roadmap's risk register.

---

## 6. Hybrid retrieval & reranking

| Repo | ★ | License | Verdict |
|---|---|---|---|
| [xhluca/bm25s](https://github.com/xhluca/bm25s) · v0.3.9 | 1.7k | MIT | **CHOSEN** — pure numpy, 1000+ qps, memory-mapped persistence |
| [dorianbrown/rank_bm25](https://github.com/dorianbrown/rank_bm25) | ~1.5k | Apache-2.0 | **REJECTED** — no release since Feb 2022 |
| [PrithivirajDamodaran/FlashRank](https://github.com/PrithivirajDamodaran/FlashRank) · v0.2.10 | 994 | Apache-2.0 | **CHOSEN** — explicitly *"no Torch or Transformers"*, CPU, 4–110 MB models |
| [FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) | ~8k | MIT | **REJECTED** — bge-reranker-v2-m3 is better, at ~2 GB torch + ~1.5 GB weights |
| [AnswerDotAI/rerankers](https://github.com/AnswerDotAI/rerankers) | ~1.5k | Apache-2.0 | Nice unified API; unnecessary indirection for one reranker |
| [stanford-futuredata/ColBERT](https://github.com/stanford-futuredata/ColBERT) | ~3k | MIT | **REJECTED** — needs a multi-vector index Chroma can't provide |

### ⚠ Ollama cannot rerank
Verified 2026-07-21: **there is no `/api/rerank` endpoint.** [PR #7219](https://github.com/ollama/ollama/pull/7219) has been open since 2024. The ecosystem routes around it with adapters like [dify-ollama-rerank-adapter](https://github.com/jtianling/dify-ollama-rerank-adapter).

This invalidated an earlier plan to rerank "via Ollama" and is why FlashRank's torch-free ONNX approach is load-bearing rather than merely convenient.

---

## 7. Evaluation

| Repo | ★ | License | Verdict |
|---|---|---|---|
| [vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) · v0.4.3 | 14.9k | Apache-2.0 | **DEFERRED** — wireable to an Ollama judge, but a 3B judge is noisy. *(Formerly `explodinggradients/ragas`.)* |
| [confident-ai/deepeval](https://github.com/confident-ai/deepeval) · v4.1.2 | ~4k | Apache-2.0 | **DEFERRED** — pytest-native and pleasant; same judge-quality problem |
| [stanford-futuredata/ARES](https://github.com/stanford-futuredata/ARES) | ~1k | MIT | Reference for the golden-set methodology |
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | ~10.8k | MIT | Reference for YAML-declared test cases |

**We build a small harness instead.** Retrieval metrics (Recall@k, MRR, nDCG@10) need no judge model — they are arithmetic over a golden set. Deterministic, fast, runs in pytest. Reasoning in [RESEARCH.md §7](RESEARCH.md#7-evaluation).

---

## 8. Corpus: sources and licensing

**The licensing situation is a real finding, not paperwork.** The spec lists ISO 27001 as an example standard; shipping it would be copyright infringement.

| Standard | Source | Licence | Ship it? |
|---|---|---|---|
| **NIST CSF 2.0** | [NIST.CSWP.29.pdf](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf) | US Gov — **public domain** | ✅ Yes |
| **NIST SP 800-53 Rev 5** | [NIST.SP.800-53r5.pdf](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf) | Public domain | ✅ Yes — our stress test (400+ pages, dense tables) |
| **NIST SP 1299** (CSF 2.0 guide) | [NIST.SP.1299.pdf](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1299.pdf) | Public domain | ✅ Yes |
| **OWASP Top 10** | [owasp.org/Top10](https://owasp.org/Top10/) · markdown at [github.com/OWASP/Top10](https://github.com/OWASP/Top10) | CC-BY-4.0 | ✅ Yes, with attribution — **no PDF exists** for the 2021/2025 editions (see note below) |
| **OWASP ASVS** | [owasp.org/…verification-standard](https://owasp.org/www-project-application-security-verification-standard/) | CC-BY-SA | ✅ Yes, with attribution |
| **CIS Controls v8.1** | [cisecurity.org](https://www.cisecurity.org/controls) | Free w/ registration; redistribution restricted | ⚠️ Fetch script only — never committed |
| **ISO/IEC 27001:2022** | ISO store (~£220+) | **Copyrighted** | ❌ **Excluded** |

**How this is handled:** `scripts/fetch_docs.py` downloads the freely-redistributable set; one or two small public-domain samples are committed so the repo is runnable on clone; the README states the ISO 27001 position plainly.

> **Correction, found during T-0.3.** OWASP stopped shipping the Top 10 as a PDF after the 2017 edition — 2021 and 2025 are published as MkDocs markdown only, and every plausible `.pdf` URL 404s. The fetch script therefore assembles the official English markdown (`2021/docs/en/`) into a single attributed TXT. This is a happy accident for the project: it means the corpus exercises both the TXT and PDF paths from Phase 1 onward rather than being PDF-only, and the CC-BY attribution requirement is satisfied by a provenance header the script prepends.

A reviewer who notices you *correctly declined* to ship a copyrighted standard learns more about your judgement than one who sees a complete corpus. It also demonstrates the extensibility the spec asks for: a user with a licensed ISO copy drops it into `docs/` and it just works.

### Domain-specific references
- **[An Empirical Study of Knowledge Graph-Enhanced RAG for Information Security Compliance](https://doi.org/10.3390/info17040389)** — *Information* 17(4):389, April 2026. **The closest published prior art to this project**: LightRAG + locally-hosted open models over ISO 27001. Its central finding independently supports our design — that independent chunking plus dense-only retrieval *"prove inadequate for such highly interconnected regulatory materials, often fragmenting contextual relationships and reducing accuracy."* That is precisely the failure our hybrid retrieval and parent–child hierarchy exist to prevent. Read it before Phase 3.
- [mikeprivette/NIST-to-Tech](https://github.com/mikeprivette/NIST-to-Tech) — NIST control → technology mappings, useful for golden-set questions

---

## Read these 8 first

1. **[Cinnamon/kotaemon](https://github.com/Cinnamon/kotaemon)** — nearest neighbour to our project. Hybrid retrieval, reranking, citations with source viewing, Ollama support. Study its citation UI before designing ours.
2. **[xhluca/bm25s](https://github.com/xhluca/bm25s)** — small enough to read end to end. Understanding BM25 concretely is what makes hybrid retrieval feel obvious rather than magical.
3. **[PrithivirajDamodaran/FlashRank](https://github.com/PrithivirajDamodaran/FlashRank)** — ~1k lines. Read it to see how little a cross-encoder reranker actually is once torch is out of the picture.
4. **[jsvine/pdfplumber](https://github.com/jsvine/pdfplumber)** — read the table-extraction docs specifically. Table quality determines answer quality on SP 800-53, and this is where that battle is won.
5. **[feyninc/chonkie](https://github.com/feyninc/chonkie)** — read `RecursiveChunker` for the algorithm, then write our control-aware version deliberately.
6. **[zylon-ai/private-gpt](https://github.com/zylon-ai/private-gpt)** — for its ingestion-layer interfaces. This is where "modular and maintainable" stops being a slogan.
7. **[infiniflow/ragflow](https://github.com/infiniflow/ragflow)** — for document understanding and grounded citation design. Skim, don't read; it's large and polyglot.
8. **[onyx-dot-app/onyx](https://github.com/onyx-dot-app/onyx)** — for how a serious codebase does hybrid search and genuine air-gapped operation.

**Suggested order:** 2 and 3 first — both small enough to fully understand, and both core to Phase 3. Then 4 and 5 before writing the ingestion pipeline. Then 1 and 6 as architectural sanity checks. 7 and 8 are skim-only.

---

## Verified stack versions

Confirmed on PyPI, 2026-07-21. `uv` will resolve current versions at install time; these are the floor.

| Library | Version | Licence | Role |
|---|---|---|---|
| `ollama` | 0.6.2 | MIT | All inference |
| `streamlit` | 1.59.2 | Apache-2.0 | UI (mandated) |
| `chromadb` | 1.5.9 | Apache-2.0 | Vector store |
| `bm25s` | 0.3.9 | MIT | Keyword retrieval |
| `flashrank` | 0.2.10 | Apache-2.0 | Reranking |
| `pypdf` | 6.14.2 | BSD-3 | PDF text |
| `pdfplumber` | 0.11.10 | MIT | PDF tables + coordinates |
| `pydantic-settings` | 2.14.x | MIT | Config |
| `docling` | 2.114.0 | MIT | Default PDF parser |

Python target: **3.12** — every dependency above ships wheels, and it avoids the 3.13/3.14 wheel gaps that still affect parts of the ML ecosystem.
