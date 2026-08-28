# CSRS — Cybersecurity Standards RAG System

![Python 3.12](https://img.shields.io/badge/python-3.12-3776ab)
![Ollama](https://img.shields.io/badge/LLM-Ollama%20(local)-000000)
![Offline](https://img.shields.io/badge/runtime-100%25%20offline-fb7185)
![Tests](https://img.shields.io/badge/tests-343%20offline-34d399)

Ask questions about cybersecurity standards and get answers grounded in the documents
themselves, with page-level citations. Everything runs locally: the language models, the
embeddings, and the vector store. **No cloud API is used or permitted.**

## Internship final submission

This submission maps directly to the three required deliverables:

| Requirement | Submission evidence | How to inspect or reproduce it |
|---|---|---|
| 1. Final report | `CSRS_Work_Record.pdf`; source: `latex/CSRS_Work_Record.tex` | Run `./latex/build.sh` to rebuild the report PDF. The PDF is a generated submission artefact and is intentionally excluded from Git. |
| 2. Presentation (at least 30 slides) | `CSRS_Presentation.pptx` — **33 slides**; PDF backup: `CSRS_Presentation.pdf`; source: `latex/CSRS_Presentation.tex` | Run `./latex/build.sh --slides`, then `python scripts/export_pdf_to_pptx.py CSRS_Presentation.pdf CSRS_Presentation.pptx` to rebuild both formats. |
| 3. Public GitHub repository with week-wise/day-wise code, data, and execution documentation | [github.com/subhan-17h/CSRS](https://github.com/subhan-17h/CSRS); day index: [`project-docs/DAY_INDEX.md`](project-docs/DAY_INDEX.md); verified history: [`project-docs/PROJECT_WORK_HISTORY.md`](project-docs/PROJECT_WORK_HISTORY.md); code: [`src/csrs/`](src/csrs/) and [`frontend/`](frontend/); final alert-ranking data: [`artifacts/alert-ranking-v3/`](artifacts/alert-ranking-v3/); evaluation data: [`eval/data/`](eval/data/); execution documentation: this README and [`project-docs/Submission.md`](project-docs/Submission.md) | Run `git tag -n99 -l 'day-*'` to list annotated working-day checkpoints, then `git show day-01-2026-07-21` (or another tag) to inspect a day. Follow [Quick start](#quick-start) to run the application. |

The repository preserves copyright and licensing boundaries: its source code is MIT licensed,
while restricted standards and generated local indexes are not redistributed. See
[What ships, and what doesn't](#what-ships-and-what-doesnt).

<img src="assets/architecture.svg" alt="CSRS architecture: the ingest and query pipelines, the Pipeline facade both interfaces call, and the offline boundary enclosing Ollama" width="100%">

```
Question → nomic-embed-text ─┬─→ Chroma (cosine) ─┬─ RRF ─→ top 5 → llama3.2 → grounded answer
                             └─→ BM25 (bm25s) ────┘
```

Built on [Ollama](https://ollama.com), with
[Docling](https://github.com/docling-project/docling) for layout-aware PDF parsing.

**New here?** [Submission.md](project-docs/Submission.md) is the component-by-component walkthrough:
what each module does, which task requirement it satisfies, and how the pieces connect.

**Reading the work day by day?** [DAY_INDEX.md](project-docs/DAY_INDEX.md) maps all 32 days of the
internship to their commits, artefacts and tags; [PROJECT_WORK_HISTORY.md](project-docs/PROJECT_WORK_HISTORY.md)
is the verified narrative. Thirteen annotated tags (`git tag -n99 -l 'day-*'`) let you check out any
working day.

### Two interfaces, one pipeline

Both talk to the same `Pipeline` facade and give the same grounded answers.

| | **Web UI** (React + FastAPI) | **Streamlit** |
|---|---|---|
| Run | `uv run csrs-api` | `uv run streamlit run src/csrs/app.py` |
| URL | http://127.0.0.1:8000 | http://localhost:8501 |
| Answers stream token by token | yes | no |
| Live retrieval progress | yes | indexing only |
| **Citations shown** | **yes — page, section, control ID, score** | no |
| Corpus browser | yes — read the source PDF/TXT, plus a chunk browser | document list only |
| Conversation history | yes (local, in-browser) | no |
| Extra requirement | Node 18+ to build once | none |

The Streamlit app is the interface the task specification asks for and is kept intact. The
web UI was added on top of the finished pipeline; it renders the citations the Streamlit
interface never displayed, which is the main reason it exists.

The reasoning behind each choice — and the measurements that drove it — is in
[Submission.md](project-docs/Submission.md). The diagram above is also available as a browsable page
with PNG and PDF export: `assets/architecture.html`.

---

## Quick start

Five commands, assuming [Ollama](https://ollama.com/download) and
[uv](https://docs.astral.sh/uv/getting-started/installation/) are installed:

```bash
uv sync                                              # 1. Python dependencies
ollama serve &                                       # 2. start Ollama (skip if already running)
uv run python scripts/warm_models.py --pull-ollama   # 3. models: ~14 GB Ollama + ~1.3 GB Docling
python scripts/fetch_docs.py                         # 4. corpus (stdlib only, no venv needed)
```

Then start **either** interface:

```bash
# Web UI — build the frontend once, then serve everything on one port
(cd frontend && npm install && npm run build)
uv run csrs-api                                      # http://127.0.0.1:8000

# or Streamlit
uv run streamlit run src/csrs/app.py                 # http://localhost:8501
```

> **The first launch takes longer than later starts** while the 32-page CSF PDF is parsed
> through a layout model and indexed. Every launch after that reuses the content-hashed
> index and starts in well under a second. See
> [Why the first run is slow](#why-the-first-run-is-slow).

---

## Installation

### 1. Prerequisites

| Requirement | Why | Install |
|---|---|---|
| **Python 3.12** | Pinned in `.python-version`; `uv` fetches it if absent | handled by `uv` |
| **uv** | Lockfile-based reproducible installs | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Ollama** | Runs every model locally | [ollama.com/download](https://ollama.com/download) |

Roughly **20 GB of free disk** is needed: ~14 GB of Ollama models, ~1.3 GB of Docling
weights, and ~150 MB of corpus and index.

### 2. Python dependencies

```bash
uv sync
```

Installs from `uv.lock`, so the environment is byte-for-byte reproducible. Dependencies are
declared in `pyproject.toml` (there is no `requirements.txt`; the lockfile supersedes it).

### 3. Start Ollama

```bash
ollama serve
```

Leave it running. On macOS, `brew services start ollama` runs it as a persistent background
service instead, which survives reboots and is what we'd recommend.

Verify it is reachable:

```bash
curl -s http://127.0.0.1:11434/api/tags | head -c 80
```

### 4. Download the models

```bash
uv run python scripts/warm_models.py --pull-ollama
```

One command fetches everything the application needs to run offline:

- the mandatory embedding model, **`nomic-embed-text`**;
- all five supported LLMs — `llama3.2`, `qwen2.5:1.5b`, `gemma2:2b`, `phi4-mini`,
  `gemma4:e2b`;
- Docling's layout and TableFormer weights (OCR weights are deliberately *not* fetched — the
  corpus is digital-native, so OCR is never used).

It is idempotent: run it again and everything already present is skipped. Without
`--pull-ollama` it reports what is missing and prints the `ollama pull` commands rather than
downloading several gigabytes unasked.

Expected output ends with:

```
Summary:
  Docling: ready
  Ollama: 6 of 6 required models present
  FlashRank: ready

All required model weights are present.
```

(The FlashRank weights are the cross-encoder reranker. It ships disabled — see
[Known limitations](#known-limitations) — but the weights are fetched here so that turning
it on never needs the network.)

**This is the only step that needs the internet.** Everything after it is fully offline.

### 5. Get the corpus

```bash
python scripts/fetch_docs.py
```

Deliberately stdlib-only, so it works with the system Python *before* `uv sync` if you like.
It downloads the two large NIST standards and skips anything already committed. Use
`--force` to re-download.

Most standards are **not** committed to the repository for licensing reasons — see
[What ships, and what doesn't](#what-ships-and-what-doesnt).

---

## Running the application

### Web UI

Build the frontend once, then FastAPI serves the built assets and the API together on a
single port:

```bash
(cd frontend && npm install && npm run build)
uv run csrs-api
```

Open **http://127.0.0.1:8000**. It binds to loopback only — there is no authentication
because nothing off your machine can reach it.

While working on the frontend, run it in dev mode instead. Two processes, with Vite
proxying `/api` to the backend:

```bash
uv run uvicorn csrs.api.app:app --host 127.0.0.1 --port 8000   # terminal 1
cd frontend && npm run dev                                     # terminal 2 -> :5173
```

The interface gives you:

- a **question box**, with answers **streaming in token by token** and live retrieval stages;
- **citations** under every answer — document, page, section breadcrumb, control ID and
  cosine score, expandable to the retrieved text;
- a sidebar of **application settings** — model selector, `top_k`, temperature, and a live
  Ollama indicator;
- the **list of indexed documents** with page and chunk counts;
- **Restart & Reload Documents**, plus a full rebuild behind a confirmation;
- a **Corpus** tab that shows each indexed document two ways: the **source file itself**, PDFs rendered page by page and TXT typeset, and the **chunks** the pipeline built from it;
- **conversation history**, stored in your browser only, with follow-up questions rewritten into standalone queries before retrieval.

### Streamlit

```bash
uv run streamlit run src/csrs/app.py
```

Open **http://localhost:8501**. It offers the question box, the generated answer with the
model named underneath, the sidebar settings, the indexed-document list, and the reload
buttons. Another port: `--server.port 8502`.

Both interfaces read the same index, so you can run them at once. Only trigger a **rebuild**
from one of them at a time.

### Stopping and restarting

**The daemons are cheap; loaded models use the memory.** Ollama normally keeps a model
loaded for five minutes after a query, and CSRS extends that to 30 minutes for the answer
model through `CSRS_KEEP_ALIVE`. Model weights consume gigabytes; the idle processes only
consume tens of megabytes:

| Process | Role | Idle resident memory |
|---|---|---:|
| `ollama serve` | Local model server, running as a Homebrew service | ~20 MB |
| `csrs-api` | FastAPI backend and built Web UI | ~21 MB |
| `vite` | Frontend dev server, only during frontend work | ~50 MB |

So unloading the model weights is usually more useful than shutting down the server:

```bash
ollama ps                 # show the models resident in memory
ollama stop <model-name>  # unload one model
```

To stop everything:

```bash
pkill -f 'csrs-api'
pkill -f 'frontend/node_modules/.bin/vite'
pkill -f 'streamlit run src/csrs/app.py'
brew services stop ollama
```

Ctrl-C in the terminal that owns `csrs-api`, Vite, or Streamlit works too. If the development
backend shown above is running instead of `csrs-api`, use Ctrl-C in its terminal or run
`pkill -f 'uvicorn csrs.api.app:app'`. Ollama is a Homebrew service, so it restarts at login
unless it is stopped with `brew services stop ollama`.

Check the four application ports:

```bash
lsof -nP -iTCP:8000 -iTCP:5173 -iTCP:8501 -iTCP:11434 -sTCP:LISTEN
```

No output means everything is down. To bring it back, run `brew services start ollama`, then
use the Web UI, frontend development, or Streamlit commands already documented above.

**Stopping these processes does not cost a re-index.** The persistent 35 MB index lives in
`chroma_db/` — including `chroma.sqlite3`, Chroma's vector index files, and `manifest.json` —
and survives every process restart. Startup runs an incremental index check, not a full
rebuild. At `src/csrs/pipeline.py:127`, each file's SHA-256 is compared with the manifest;
unchanged files are skipped before parsing or embedding. With an unchanged corpus, that
check takes about 40-80 ms and makes zero embedding calls. See
[Adding new documents](#adding-new-documents) for how the content hashes work.

Only three things force the roughly 316-second cold rebuild:

1. `POST /api/index/rebuild` or `Pipeline.index(force=True)`, including the
   **Full Rebuild Documents** button.
2. Deleting or moving `chroma_db/`.
3. A disagreement between the store and manifest. The consistency guard at
   `src/csrs/pipeline.py:111-117` resets and rebuilds when manifest identities are invalid
   or the stored chunk counts do not match the manifest.

Only the third can happen by accident — kill a process mid-index, after the store and
manifest have diverged. Processes can be stopped freely whenever an index run is not in
flight.

One quick sanity check:

```bash
python3 -c "import json;m=json.load(open('chroma_db/manifest.json'));print(len(m),sum(r['chunk_count'] for r in m.values()))"
```

For the shipped index, it prints:

```text
1 209
```

### Try these

Useful questions for the shipped CSF-only corpus include:

- *What are the six Functions of the NIST Cybersecurity Framework?*
- *How do Current and Target Profiles differ?*
- *What do the four CSF Tiers characterize?*
- *Which outcomes belong to the GOVERN Function?*
- *What does ISO 27001 require for access control?* — this should refuse.

**On that last one:** ISO 27001 is not freely redistributable, so it is not in the shipped
corpus. Refusing is the system working — it declines rather than answering from the CSF
document it *does* have. Add your own licensed copy to `docs/`, reload, and the question
answers.

Ask something plainly outside the documents — *What is the best recipe for chocolate chip
cookies?* — and it refuses too, while still showing which passages it retrieved and judged
insufficient.

---

## Adding new documents

**Drop a file into `docs/` and press "Restart & Reload Documents". That's the whole process.**

```bash
cp ~/Downloads/CIS_Controls_v8.1.pdf docs/
```

No code change, no restart, no configuration. `.pdf` and `.txt` are supported, and
subdirectories are scanned too. The new file is parsed, chunked, embedded and queryable — a
small document lands in well under a second.

Two buttons, because they cost very different amounts:

| Button | What it does | When |
|---|---|---|
| **Restart & Reload Documents** | Indexes only what changed | Almost always |
| **Full Rebuild Documents** | Reprocesses everything (~5 min) | Only if the index looks wrong |

The reload is incremental because every file is fingerprinted by a SHA-256 of its **bytes**,
checked *before* the parser runs. Unchanged files are skipped without being opened, changed
files are reprocessed, and deleted files have their chunks removed. Content is hashed rather
than modification time, so a `git checkout` — which rewrites mtimes constantly — does not
trigger a five-minute rebuild.

One constraint: **filenames must be unique** across `docs/`, including subdirectories.
Duplicate names are rejected with a clear error rather than silently indexed twice.

---

## Configuration

Every production tunable lives in `src/csrs/config.py` and can be overridden by an
environment variable or a `.env` file, all prefixed `CSRS_`. Copy `.env.example` to `.env`
to start. `GROQ_API_KEY` is evaluation-only and is ignored unless the developer explicitly
runs the evaluator with `--judge`.

```bash
CSRS_DEFAULT_LLM=qwen2.5:1.5b     # faster, less reliable at staying grounded
CSRS_RETRIEVAL_MODE=dense         # 'hybrid' (default) fuses BM25 with dense; 'dense' is semantic only
CSRS_TOP_K_DENSE=20               # retrieval candidate pool
CSRS_RERANK_TOP_N=5               # chunks that actually reach the model
CSRS_RERANK_ENABLED=true          # cross-encoder rerank; off by default, see limitations
CSRS_CHUNK_SIZE=400               # approximate tokens
CSRS_PDF_PARSER=pypdf             # emergency fallback; see below
```

`CSRS_EMBED_MODEL` exists but should not be changed. `nomic-embed-text` is mandated by the
spec, and `embeddings.py` applies that model's specific `search_document:` / `search_query:`
task prefixes. Pointing it at another model would silently degrade retrieval rather than
fail loudly.

---

## What ships, and what doesn't

One standard is committed in `docs/samples/`, so a fresh clone is queryable with no
download at all:

| File | Licence |
|---|---|
| `NIST.CSWP.29_CSF-2.0.pdf` | US Government work — public domain |

`scripts/fetch_docs.py` verifies this committed sample by default and refreshes the same
path from NIST when called with `--force`.

Two of the standards named in the task specification are **deliberately absent**:

- **ISO/IEC 27001:2022** is copyrighted and sold by ISO. Shipping it would be infringement,
  so it is excluded. Asking *"What does ISO 27001 require for access control?"* therefore
  returns a refusal — **that is correct behaviour**, not a bug. Drop a licensed copy into
  `docs/` and it works like any other document.
- **CIS Controls v8.1** is free but requires registration, and its terms restrict
  redistribution. Same story: download it yourself, drop it in.

Full licensing detail for the corpus is in [docs/README.md](docs/README.md).

**This project's own code is MIT licensed** — see [LICENSE](LICENSE). That covers the source
only; the standards under `docs/` remain under their publishers' terms.

---

## Answer quality, measured

The current benchmark is the readable `eval/data/ground_truth.json`: 50 draft questions
derived from exact evidence in NIST CSF 2.0. The end-to-end evaluator compares three
independent layers instead of hiding failures in one score:

1. Local answer cosine similarity with `nomic-embed-text:latest`.
2. Raw English RoBERTa-large BERTScore precision, recall, and F1.
3. Optional evidence-aware Groq judging with `openai/gpt-oss-120b`.

Run the default five-model comparison without a cloud judge:

```bash
uv run --group eval python -m eval.run
```

Add `--judge` only after setting `GROQ_API_KEY` in the ignored root `.env`. Normal FastAPI,
Streamlit, indexing, and chat operation never call Groq and remain fully offline.

Each run writes `config.json`, question-level `results.jsonl` and `results.csv`,
`summary.csv`, `report.md`, and `manual_review.json`. Cosine uses a fixed `0.75` pass
threshold; BERTScore uses raw F1 `0.85`. Neither proves factual correctness, and the judge
is not a substitute for expert review. See [the evaluation plan](docs/EVALUATION_PLAN.md)
for the rubric, fixed comparison settings, limitations, and deferred work. The
[evaluation README](eval/README.md) explains the three techniques and links the final
five-model results.

The completed 250-row judged run had zero technical errors:

| Model | Mean cosine / pass | Mean BERT F1 / pass | Judge pass |
|---|---:|---:|---:|
| `gemma2:2b` | 0.848 / 82% | 0.910 / 100% | 90% |
| `gemma4:e2b` | 0.840 / 76% | 0.905 / 98% | 82% |
| `llama3.2:latest` | 0.817 / 74% | 0.887 / 96% | 76% |
| `phi4-mini:latest` | 0.802 / 64% | 0.878 / 86% | 50% |
| `qwen2.5:1.5b` | 0.785 / 48% | 0.883 / 90% | 44% |

The metrics remain independent; this table does not define a combined score. Exact
question-level results are in [`eval/final/results.csv`](eval/final/results.csv), with
aggregates in [`eval/final/summary.csv`](eval/final/summary.csv) and methodology in
[`eval/final/report.md`](eval/final/report.md).

---

## Known limitations

Stated plainly, because a system that hides its failure modes is harder to trust than one
that names them. Measurements and analysis are in [Submission.md](project-docs/Submission.md).

**Conversational memory is shallow, and only in the web UI.** Follow-up questions work:
the last two turns are used to rewrite a question like *"Explain the Identify function."*
into a standalone search query before retrieval. But it is query rewriting, not a
conversation — the model answers each question from retrieved context alone and remembers
nothing it previously said, and only two turns back are considered. **The Streamlit app has
no history at all**; each question there is independent, so name the standard in the
question when using it.

**Multi-turn quality is not measured.** The current 50-question benchmark is single-turn,
so the evaluator cannot score rewriting. Its evidence is a worked example rather than a
number — weaker than the measured evaluation layers, and worth saying out loud.

**Reranking is built but disabled.** A cross-encoder rerank puts the right chunk first far
more often — 33 of 37 questions versus 29 — and costs **1.6 s per query** on this hardware,
against a ~30 ms budget. flashrank's smaller model runs in 82 ms but ranks *worse than no
reranking at all*. There is no middle option in its model registry, so `rerank_enabled`
ships `False`. Turn it on with `CSRS_RERANK_ENABLED=true` if you would rather have the
precision than the second and a half.

**Parent–child retrieval is not built.** The model receives the exact retrieved passages,
with no expansion to their surrounding section. Grounding is honest but sometimes narrower
than a reader would like.

**Smaller models are less reliable.** All five required LLMs are selectable, but they are not
equally good at staying grounded. `qwen2.5:1.5b` has been observed refusing a question that
is squarely *in* the corpus and that `llama3.2` and `gemma2:2b` both answered from identical
retrieved chunks. Re-measured through the API: *"What does control AC-2 require for account
management?"* is refused by `qwen2.5:1.5b` at both `top_k=3` and `top_k=5`, and answered by
`llama3.2` at both — so it is the model, not the amount of context. `llama3.2` is the default
for this reason. **If you switch models and start seeing refusals, switch back before
concluding retrieval is broken.**

**Citations are structural, not inline.** The web UI shows every retrieved chunk with its
document, page, section breadcrumb, control ID and score. What it cannot do is mark *which
sentence* came from *which* source: the model does not emit citation markers, so attributing
individual claims would mean guessing. The sources are what was retrieved and given to the
model, not a per-claim provenance trail. The Streamlit interface does not display them at
all.

**The web UI needs Node once.** Building `frontend/dist` requires Node 18+. After that the
build is static and the app is fully offline. The Streamlit interface needs no Node at all,
so the project remains runnable on a machine without it.

**Deleting `chroma_db/` while the app is running** leaves a stale database handle and
produces a readonly error. Restart the app. Don't delete the index out from under a live
process.

---

## Why the first run is slow

PDFs are parsed by **Docling**, which runs a real document-layout model over every page
rather than scraping the text layer. The shipped corpus is now one 32-page document that
produces 209 chunks, so its first index is much smaller than the earlier four-document
stress corpus.

It buys structural correctness that regex heuristics could not deliver. Running headers and
footers are classified as furniture and dropped by construction; tables come out as real
Markdown tables; section headings are identified as headings. An earlier hand-rolled parser
needed four rounds of increasingly specific rules to suppress SP 800-53's page furniture, and
each round was only found by testing against a document the previous round hadn't seen. That
approach doesn't extend to standards nobody has looked at yet — which is precisely what the
"drop a new document in" requirement asks for.

The cost is paid once. Because the index is content-hashed, a restart with an unchanged
corpus reloads in **0.057 s**.

If you need speed over fidelity, `CSRS_PDF_PARSER=pypdf` selects a fast text-layer fallback.
It degrades honestly — thinner section breadcrumbs, less reliable furniture removal — and is
an emergency path, not a supported quality tier.

---

## Development

```bash
uv run ruff check .                                              # lint
CSRS_OLLAMA_HOST=http://127.0.0.1:9 uv run pytest -q -m "not ollama and not docling"
uv run pytest -q -m docling                                      # needs Docling weights
uv run pytest -q -m ollama                                       # needs a live Ollama
uv run --group eval python -m eval.run --limit 1 --models llama3.2:latest
```

The offline suite (343 tests) points at a dead port on purpose: it proves nothing silently
reaches the network. Tests needing real models are marked and deselected by default.

### Project layout

```
src/csrs/
  config.py       every tunable, typed, in one place
  models.py       Chunk, Document, RetrievedChunk, Answer
  loaders/        docling_parser.py (default) | pdf.py (fallback) | text.py
  chunking.py     structure-aware splitter, emits hierarchy breadcrumbs
  embeddings.py   the only module that owns the nomic task prefixes
  store.py        Chroma + the content-hash manifest
  retrieval.py    BM25 index, RRF fusion, reranking, the one retrieve() both UIs reach
  generation.py   prompt assembly, grounding instruction, refusal, token streaming
  pipeline.py     the single facade both UIs talk to
  app.py          Streamlit
  api/app.py      FastAPI — chat, streaming, index control, corpus, static hosting

frontend/
  src/App.tsx           chat orchestration and the streaming send flow
  src/lib/api.ts        the only module that knows the HTTP contract
  src/lib/history.ts    localStorage persistence
  src/components/       SourcesCard (citations), CorpusExplorer, Sidebar, Composer
  public/fonts/         woff2 vendored locally so the UI never calls a CDN

eval/
  data/ground_truth.json    50 readable evidence-grounded draft questions
  data/corpus_manifest.json exact corpus identity and extraction metadata
  dataset.py                schema, loading, and corpus-grounding validation
  metrics.py                cosine similarity and raw BERTScore P/R/F1
  judge.py                  opt-in Groq structured judge and cache
  reporting.py              JSONL, detailed/summary CSV, Markdown, and review exports
  run.py                    end-to-end comparison CLI
  final/                    tracked outputs created after the 250-row acceptance gate

project-docs/
  DAY_INDEX.md              all 32 days mapped to commits, artefacts and tags
  PROJECT_WORK_HISTORY.md   the verified day-by-day narrative and full commit ledger
  Submission.md             requirements walkthrough, decisions, and measurements
  ROADMAP.md                the task breakdown, phase by phase
  RESEARCH.md               the techniques surveyed before building
  CSRS.md                   the original task specification
  OS_REPOS.md               open-source landscape survey

assets/
  architecture.svg          the diagram at the top of this file
  architecture.html         same diagram, browsable, with PNG/PDF export

scripts/
  warm_models.py            fetches every model weight; the only step needing the internet
  fetch_docs.py             downloads the two large NIST standards; stdlib only
```

**`pipeline.py` is the load-bearing boundary.** Neither UI imports Chroma, Ollama or the
manifest — both only call the facade. That rule is enforced by review and is exactly what
made the second interface possible without touching the retrieval or generation code.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Could not connect to Ollama` | It isn't running. `ollama serve`, or `brew services start ollama` |
| Sidebar warns models are missing | `uv run python scripts/warm_models.py --pull-ollama` |
| `DoclingSetupError` on startup | Weights absent. `uv run python scripts/warm_models.py`, or set `CSRS_PDF_PARSER=pypdf` |
| App looks frozen on first launch | Expected — the ~5 min cold index. Watch the terminal |
| No documents listed | `docs/` is empty. `python scripts/fetch_docs.py` |
| `Document filenames must be unique` | Two files share a basename across `docs/`. Rename one |
| Readonly database error | `chroma_db/` was deleted while running. Restart the app |
| Web UI shows a blank page | `frontend/dist` was never built. `cd frontend && npm install && npm run build` |
| Web UI loads but cannot answer | The API is not running, or is on another port. `uv run csrs-api` |
| `An index operation is already in progress` | A reload or rebuild is running. Wait for it — they are deliberately not concurrent |
| Composer is disabled | The sidebar states why: Ollama down, no model installed, or an index run in progress |
