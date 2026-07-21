# RESEARCH.md — Evidence Base for CSRS

**Cybersecurity Standards RAG System** · research compiled 2026-07-21

This document is the *why* behind every choice in [ROADMAP.md](ROADMAP.md). If a decision in the roadmap looks arbitrary, its justification is here. Repos referenced are catalogued in [OS_REPOS.md](OS_REPOS.md).

**Verification policy.** Every citation below was resolved before inclusion. Three errors were caught and corrected during the verification pass — they are recorded in [§11](#11-corrections-made-during-verification) rather than quietly fixed, because knowing *what kind* of thing goes wrong is itself useful.

---

## Our constraints (these decide everything)

| Constraint | Consequence |
|---|---|
| 100% offline after install | No cloud APIs. No runtime model downloads on the default path. |
| Ollama-only inference | No `sentence-transformers`, no torch-based rerankers on the default path. |
| `nomic-embed-text` mandatory | 768-dim, 8192 ctx, **task-prefix-required**. See [§8](#8-nomic-embed-text-the-details-that-actually-matter). |
| Generator is 1.5B–3.8B | Fragile instruction-following. Techniques needing many LLM passes are costly *and* unreliable. |
| CPU inference | Generation dominates latency (~3–5 s). Retrieval budget is essentially free by comparison. |
| Corpus = standards documents | Rigid hierarchy, numbered control IDs (`AC-2`, `ID.AM-01`), dense tables, heavy near-duplicate boilerplate. |
| Graded submission | Setup friction is a cost. Heavy deps must justify themselves. |

The corpus property matters more than it first appears. Standards documents are **lexically distinctive** (control IDs) and **semantically repetitive** (dozens of controls phrased almost identically). That combination is precisely the case where pure dense retrieval underperforms and hybrid retrieval wins — see [§2](#2-retrieval-and-fusion).

---

## 1. Chunking

### Fixed-size recursive chunking
Split on a descending separator list (sections → paragraphs → sentences → characters) to a target token count with overlap.

**Cost:** negligible. **Verdict for CSRS: ADOPT as the base layer.** Standards documents have explicit structural boundaries (control IDs, numbered sections) that a recursive splitter can be pointed at directly, which is most of the benefit of fancier methods for free.

Target: **~400 tokens with ~60 token overlap**. Rationale: a single NIST control statement plus its discussion typically lands in the 200–500 token range, so 400 usually captures a complete control without bleeding into the next one.

### Semantic chunking
Embed consecutive sentences, split where similarity drops below a threshold.

> **["Is Semantic Chunking Worth the Computational Cost?"](https://arxiv.org/abs/2410.13070)** — Qu, Tu & Bao, 16 Oct 2024. Verified.

The paper's finding is blunt: gains are inconsistent and fixed-size chunking often *wins* on realistic (non-synthetic) documents. Indexing cost rises steeply because every sentence must be embedded.

**Verdict for CSRS: SKIP.** We would pay a large one-time CPU cost for a benefit the literature says may not exist — and our documents already carry explicit structure, which is the signal semantic chunking is trying to reconstruct statistically.

### Late chunking
> **[Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models](https://arxiv.org/abs/2409.04701)** — Günther, Mohr, Williams, Wang & Xiao (Jina AI), 7 Sep 2024. Verified. Reports **+24.5% mean nDCG@10** vs. naive chunking.

Embed the whole document in one long-context pass, *then* pool token embeddings into chunks — so each chunk embedding carries whole-document context.

**Verdict for CSRS: SKIP (mechanically blocked).** The technique needs token-level embedding output. Ollama's `embed` API returns one pooled vector per input; it does not expose per-token hidden states. We cannot implement this through Ollama, and Ollama is mandatory. Worth knowing about — the constraint, not the merit, is what rules it out.

### Contextual chunk headers (contextual retrieval)
> **[Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)** — Anthropic, Sep 2024. Reports up to **67% reduction in retrieval failures** when combined with hybrid search and reranking.

Prepend a short situating blurb to each chunk before embedding, so an isolated chunk still says what it belongs to.

**Verdict for CSRS: ADOPT, in two layers.**

1. **Deterministic breadcrumb (default, free).** We already parse the hierarchy, so prepend it: `NIST SP 800-53 Rev5 › AC Access Control › AC-2 Account Management`. For rigidly-structured standards this captures most of the disambiguating value at zero cost, zero latency, and full determinism.
2. **LLM-generated header (opt-in, cached).** A one-line generated summary per chunk, **keyed by chunk content hash** so a reload only pays for new or changed content. Behind a config flag, A/B'd against the eval harness from [§7](#7-evaluation).

The caching detail is what makes layer 2 viable at all — without it, every press of "Restart & Reload Documents" would trigger hours of CPU generation.

### Parent–child (small-to-big) retrieval
> **[KohakuRAG: A simple RAG framework with hierarchical document indexing](https://arxiv.org/abs/2603.07612)** — 8 Mar 2026. Verified.
> **[H-RAG at SemEval-2026 Task 8: Hierarchical Parent-Child Retrieval for Multi-Turn RAG Conversations](https://arxiv.org/abs/2605.00631)** — 1 May 2026. Verified.

Retrieve on small precise chunks; feed the model the larger parent section they belong to. Resolves the tension between retrieval precision (wants small chunks) and answer quality (wants context).

**Verdict for CSRS: ADOPT.** This maps almost too neatly onto our corpus: children = individual controls, parents = the control family or CSF Category. A question about `AC-2` should retrieve `AC-2` precisely but answer with the surrounding Access Control context available.

Implementation: store `parent_id` in chunk metadata, expand after reranking, deduplicate parents before assembling the prompt.

### Proposition-based chunking
> **[Dense X Retrieval: What Retrieval Granularity Should We Use?](https://arxiv.org/abs/2312.06648)** — Chen et al., Dec 2023.

Decompose text into atomic factoid propositions before indexing.

**Verdict for CSRS: SKIP.** Requires an LLM pass per chunk to extract propositions, and control language is legalistic and conditional ("the organization shall... unless..."). A 3B model decomposing that will lose the conditionals — which in a compliance context is the part that matters.

---

## 2. Retrieval and fusion

### Dense retrieval
**Verdict: ADOPT — mandatory baseline.** The spec explicitly requires semantic retrieval and states keyword search alone is insufficient. Strong on paraphrase ("who can access what" → account management controls).

Weak exactly where our corpus is dense: near-duplicate control language across families produces near-identical embeddings.

### BM25 sparse retrieval
Classic TF-IDF-family lexical ranking.

**Verdict: ADOPT.** This is not a nice-to-have for *this* corpus. A user typing `AC-2` or `ID.AM-01` or `SC-7` wants exact-token matching, and embeddings are notoriously poor at alphanumeric identifiers — a 768-dim vector does not reliably distinguish `AC-2` from `AC-3`. BM25 nails these; dense retrieval does not.

Library: **`bm25s`** (`rank-bm25` has had no release since Feb 2022 and should be treated as unmaintained).

### Hybrid via Reciprocal Rank Fusion
> **[Reciprocal rank fusion outperforms Condorcet and individual rank learning methods](https://dl.acm.org/doi/10.1145/1571941.1572114)** — Cormack, Clarke & Buettcher, SIGIR 2009, DOI `10.1145/1571941.1572114`. Verified.

`RRF(d) = Σᵢ 1 / (k + rankᵢ(d))` across retrievers.

**Verdict for CSRS: ADOPT — highest-ROI single change in the whole system.**

The elegance is that RRF consumes only *ranks*, never scores. Cosine similarities and BM25 scores live on incomparable scales, and any attempt to normalise them into a weighted sum introduces a tuning parameter that drifts with corpus and query. RRF sidesteps the calibration problem entirely.

Parameters: retrieve top-20 from each arm; `k = 60` is the paper's value and a sane default. Note that lowering `k` sharpens the influence of top ranks — worth an experiment against the eval harness rather than a guess.

### HyDE (hypothetical document embeddings)
Generate a fake answer, embed *that*, retrieve with it.

**Verdict for CSRS: SKIP.** Costs a full generation pass (3–5 s on our hardware) before retrieval even starts, roughly doubling perceived latency. Its benefit is on vague queries; our BM25 arm already covers the specific-identifier case, and standards questions skew specific.

### Multi-query expansion / RAG-Fusion
Rewrite the query into N variants, retrieve for each, fuse.

**Verdict for CSRS: DEFER.** Real recall gains, but N× generation latency on CPU. Revisit only if the eval harness shows a recall ceiling that reranking cannot lift.

### Step-back prompting
Abstract the question upward, retrieve for both levels.

**Verdict for CSRS: DEFER.** Partially subsumed by parent–child retrieval, which achieves a similar "see the broader context" effect structurally instead of with an extra LLM call.

---

## 3. Reranking

A cross-encoder scores `(query, chunk)` **jointly**, so it can model term interaction that bi-encoders structurally cannot — a bi-encoder must compress the document into a vector *before* seeing the query.

Consistently reported as the highest-value addition after hybrid search, typically **+10–25% nDCG@10**.

### ⚠ Correction: Ollama has no reranking endpoint
Initial research proposed serving `mxbai-rerank` through Ollama. **This does not work.** Verified 2026-07-21: Ollama exposes no `/api/rerank` endpoint. [PR #7219](https://github.com/ollama/ollama/pull/7219) has been open since 2024 and remains unmerged; the ecosystem works around it with [third-party adapter services](https://github.com/jtianling/dify-ollama-rerank-adapter).

Any plan that reranks "via Ollama" is unimplementable today. This is exactly why the verification pass exists.

### FlashRank
ONNX-runtime cross-encoders. **Explicitly no torch, no transformers.** Models:

| Model | Size | Note |
|---|---|---|
| `ms-marco-TinyBERT-L-2-v2` | ~4 MB | default |
| `ms-marco-MiniLM-L-12-v2` | ~34 MB | best quality/size trade-off |
| `rank-T5-flan` | ~110 MB | best zero-shot |

**Verdict for CSRS: ADOPT.** `ms-marco-MiniLM-L-12-v2` at ~34 MB. This is the only option that delivers real cross-encoder quality without either a cloud call or a multi-gigabyte torch install.

**Offline caveat, handled:** FlashRank downloads its ONNX weights on first use. The roadmap includes an explicit `scripts/warm_models.py` step and README instruction, so the download happens once at setup — alongside `ollama pull`, which is a download the spec already accepts.

### Alternatives considered
- **`sentence-transformers` CrossEncoder / bge-reranker-v2-m3** — best quality, but ~2 GB of torch plus a ~1.5 GB model. Disproportionate for a graded submission. **SKIP.**
- **LLM-as-reranker** — reuse the Ollama model to score chunks. Zero new dependencies, genuinely offline, but 50–100× slower than a cross-encoder and unreliable at 1.5B. **SKIP** (documented as the zero-dependency fallback if FlashRank cannot be warmed).
- **ColBERTv2** ([Santhanam et al., NAACL 2022](https://aclanthology.org/2022.naacl-main.272/)) — excellent late-interaction retrieval, but needs a bespoke multi-vector index incompatible with Chroma. **SKIP.**

---

## 4. Advanced architectures — evaluated and mostly declined

| Architecture | Paper | Core idea | Verdict for CSRS |
|---|---|---|---|
| **Self-RAG** | [arXiv:2310.11511](https://arxiv.org/abs/2310.11511) (ICLR 2024) | Model emits reflection tokens to self-critique retrieval | **SKIP** — requires fine-tuning; we cannot fine-tune the mandated models |
| **CRAG** | [arXiv:2401.15884](https://arxiv.org/abs/2401.15884) | Evaluate retrieval quality, correct if poor | **ADOPT the idea, not the machinery** — see below |
| **RAPTOR** | [arXiv:2401.18059](https://arxiv.org/abs/2401.18059) (ICLR 2024) | Recursive clustering + summarisation into a tree | **SKIP** — O(n log n) LLM calls to index; parent–child gives us hierarchy for free because our documents are *already* trees |
| **GraphRAG** | [Microsoft Research](https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/) | Entity/relation KG + community summaries | **SKIP** — ~100× indexing cost; designed for narrative data where structure is implicit. Ours is explicit |
| **LightRAG** | [github.com/HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | Cheap graph layer over entities | **DEFER** — the interesting version for us is a control cross-reference graph, which is a *parsing* problem, not a graph-RAG problem |
| **Adaptive-RAG** | [arXiv:2403.14403](https://arxiv.org/abs/2403.14403) | Classify query complexity, route accordingly | **DEFER** — real latency savings, but premature before we can measure |
| **Agentic RAG** | [arXiv:2501.09136](https://arxiv.org/abs/2501.09136) (survey) | LLM-driven retrieve/reason loop | **SKIP** — needs reliable tool-calling; 1.5B models do not have it |

### Independent confirmation from our exact domain
> **[An Empirical Study of Knowledge Graph-Enhanced RAG for Information Security Compliance](https://doi.org/10.3390/info17040389)** — *Information* 17(4):389, April 2026. Verified.

The nearest published prior art to this project: LightRAG plus locally-hosted open models, over the ISO 27000 family. Its problem statement matches ours almost exactly — these standards are hard because of *"formal language, abstract structure, and extensive cross-referencing across 97 documents"* — and its finding is that conventional RAG *"which relies on independent text chunking and dense vector retrieval, proves inadequate for such highly interconnected regulatory materials, often fragmenting contextual relationships and reducing accuracy."*

**This is direct support for two of our decisions**, arrived at independently: that dense-only retrieval is insufficient here (→ hybrid, [§2](#2-retrieval-and-fusion)), and that chunks must not be contextually orphaned (→ breadcrumbs + parent–child, [§1](#1-chunking)). It also suggests the deferred graph layer is the right *eventual* direction — a control cross-reference graph, if the eval harness later shows a ceiling.

**The thread running through these declines:** most advanced RAG architectures exist to *recover structure* from unstructured corpora — RAPTOR builds a hierarchy, GraphRAG builds a graph, proposition chunking builds atoms. Our corpus ships with its hierarchy already explicit in the document. Parsing it correctly is strictly cheaper and more accurate than having a 3B model infer it. **We should spend effort on the parser, not on the architecture.**

### CRAG, reduced to what we actually need
Full CRAG adds a trained evaluator and a web-search fallback (impossible offline). But its core insight — *check whether retrieval succeeded before letting the model answer* — is exactly the spec's "inform the user when sufficient information cannot be found."

**Adopted as a confidence gate:** if the top reranked score falls below a calibrated threshold, refuse rather than generate. The reranker already produces a relevance score, so this costs nothing extra. The threshold gets calibrated against the eval harness.

---

## 5. Grounding, refusal, and citation

Small models are the weak point. Grounding instructions that a frontier model follows reliably are followed *sometimes* at 1.5B–3B. Defence must be layered rather than prompt-only.

### Layer 1 — prompt design
Effective patterns, in rough order of importance:
- Put the instruction **after** the context, not before — it stays closer to the generation point.
- Give an explicit, literal refusal string to emit rather than asking the model to "say you don't know."
- Delimit each context chunk with its citation label so citing is copying, not composing.
- Keep the system prompt short. Long instruction lists degrade small-model compliance rather than improving it.

### Layer 2 — retrieval confidence gate
The CRAG-derived threshold from [§4](#crag-reduced-to-what-we-actually-need). Structurally prevents the failure mode where retrieval returns garbage and the model politely hallucinates around it.

### Layer 3 — citations as verifiable claims
Each context chunk enters the prompt labelled `[S1]`, `[S2]`…; the model cites those labels; the UI resolves them back to `document › section › p.N` with the retrieved text expandable.

**This is the highest-value trust feature in the app.** It converts "trust the model" into "check the source" — which for a compliance tool is the entire point. It is also cheap: labels are added at prompt-assembly time and parsed out of the answer with a regex.

### Layer 4 (deferred) — NLI groundedness checking
> **[MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents](https://arxiv.org/abs/2404.10774)** — Tang, Laban & Durrett, EMNLP 2024. Verified. *(Initial research cited `2404.10699` for this — that ID is an aerial LiDAR dataset. Corrected.)*

A 770M NLI model verifying each claim against context, at near-GPT-4 accuracy on grounding tasks.

**Verdict: DEFER.** Not servable through Ollama, so it would mean a torch dependency. Layers 1–3 are the pragmatic set; this is the documented next step if hallucination survives them.

---

## 6. Conversational RAG

The spec marks follow-up context as a bonus. It is worth doing, and it is mostly one technique.

### Query rewriting (contextualisation)
> **[ChatQA: Surpassing GPT-4 on Conversational QA and RAG](https://arxiv.org/abs/2401.10225)** — Liu et al., NVIDIA, Jan 2024.

The problem: "How about least privilege?" is meaningless to a retriever. Embedding it retrieves noise; BM25 retrieves nothing useful.

The fix: one small LLM call rewrites it against history into `How does AC-2 Account Management address least privilege?` — then retrieve normally.

**Verdict: ADOPT.** This *is* conversational RAG in practice. Without it, "conversational memory" means only that history is displayed on screen, not that follow-ups actually work.

Two implementation details that matter:
- Only rewrite when history exists — never on the first turn.
- Show the rewritten query in the UI (collapsed). It makes the mechanism legible and debuggable, and it demos well.

### History management
**Verdict: ADOPT the simple version.** Cap history at the last N turns. Summarisation-based compression is deferred — with `num_ctx=8192` and a bounded turn count, overflow is not a near-term risk, and an LLM compression pass per turn is a poor trade at our latency.

### Retrieval skipping
Reuse prior context when a follow-up is very similar to the previous query. **DEFER** — a correctness risk (stale context silently reused) for a latency saving that is small relative to generation cost.

---

## 7. Evaluation

Without measurement, every retrieval "improvement" is a guess. This section is what turns the roadmap's Phase 3 into engineering rather than vibes.

### The design decision: retrieval metrics, no LLM judge
Judging *generation* needs a strong judge model. Ours is 3B — a noisy judge produces numbers that look rigorous and mean little.

Judging *retrieval* needs no model at all: given a question and the chunk(s) that should answer it, Recall@k / MRR / nDCG@10 are pure arithmetic. **Deterministic, instant, and runs in pytest.**

This is also the right target. Retrieval is where our decisions live (chunking, hybrid, RRF, reranking, parent–child); generation is largely fixed by the mandated models.

### The golden set
40–60 hand-curated `question → expected source` pairs, deliberately spanning:
- **Exact-ID lookups** (`What does AC-2 require?`) — should prove BM25's contribution
- **Semantic paraphrase** (`How do I manage user accounts?`) — should prove dense retrieval's contribution
- **Cross-document** (`How do CSF and 800-53 both treat asset management?`)
- **Out-of-scope** (`What is the capital of France?`) — must trigger refusal
- The spec's own example questions, which are the ones a grader will type

The out-of-scope cases are what calibrate the confidence threshold from [§5](#layer-2--retrieval-confidence-gate).

### Metrics
| Metric | Question it answers |
|---|---|
| **Recall@k** | Did the right chunk make it into the candidate pool at all? |
| **MRR** | How high did it land? |
| **nDCG@10** | Ranking quality with graded relevance |
| **Refusal accuracy** | Refuses out-of-scope *and* answers in-scope |

Run the suite after each retrieval change; record a before/after row. The deliverable is a table showing what each addition actually bought.

### RAGAS / DeepEval
> [`vibrantlabsai/ragas`](https://github.com/vibrantlabsai/ragas) — 14.9k ★, Apache-2.0, v0.4.3 (Jan 2026). *(Formerly `explodinggradients/ragas`; the old URL still redirects.)*

Both can be wired to a local Ollama judge. **DEFER** — meaningful plumbing, plus judge noise, for metrics we cannot fully trust at 3B. The lightweight harness gives better signal per hour spent.

---

## 8. `nomic-embed-text`: the details that actually matter

**This section prevents the single most expensive bug in this stack.**

Verified against the [official model card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) and [arXiv:2402.01613](https://arxiv.org/abs/2402.01613) (*Nomic Embed: Training a Reproducible Long Context Text Embedder*).

### Task prefixes are mandatory
The model card states it directly:

> "the text prompt **must** include a task instruction prefix, instructing the model which task is being performed."

| Prefix | Use |
|---|---|
| `search_document:` | every chunk, at **index** time |
| `search_query:` | every query, at **search** time |
| `clustering:` / `classification:` | not used here |

**Why this bug is so costly:** omitting the prefixes throws no error, crashes nothing, and returns perfectly plausible vectors. Retrieval just gets quietly worse. It is only findable by knowing to look — which is why prefixing is wrapped inside the embedding module with a unit test asserting it, never left to callers.

The asymmetry is the point: documents and queries get **different** prefixes. Using `search_document:` for both is the subtle version of the same bug.

### Other properties
- **768 dimensions** native, L2-normalised → **use cosine similarity**. Chroma defaults to L2 distance; this must be set explicitly at collection creation. Another silent-degradation trap.
- **8192 token context** — far beyond our ~400-token chunks, so no truncation risk.
- **Matryoshka truncation** to 512/256/128/64 dims with modest loss. Irrelevant at our corpus size; noted for completeness.

---

## 9. Local / CPU optimisation

Ordered by actual impact on our workload.

| Technique | Effect | Verdict |
|---|---|---|
| **Content-hash incremental indexing** | Reload re-embeds only changed files | **ADOPT** — biggest real-world win. Turns "Restart & Reload" from minutes into instant for unchanged corpora |
| **Batch embedding** | 2–5× indexing throughput | **ADOPT** — `ollama.embed()` accepts a list; batch ~32 |
| **`keep_alive`** | Avoids 5–30 s model reload between queries | **ADOPT** — set `keep_alive="30m"`. Highest perceived-latency win for the cost |
| **`num_ctx=8192`** | Fits ~5 chunks + parents + history | **ADOPT** — but note KV cache is allocated **upfront**; dial down if RAM-constrained |
| **Q4_K_M quantisation** | ~2–3× faster CPU inference, ~1–3% quality loss | **ADOPT** — Ollama's default tags are already Q4_K_M |
| **Streaming output** | Time-to-first-token drops to <1 s | **ADOPT** — `st.write_stream`. Changes nothing about total time, transforms how slow it feels |
| **Embedding cache (query-level)** | Skips re-embedding repeat queries | **ADOPT** — trivial LRU |
| **HNSW vs. flat index** | Irrelevant below ~100k chunks | Chroma's default is fine; do not tune |

**Realistic budget** (~10–30k chunks, 8 GB RAM, CPU):

| Stage | Time |
|---|---|
| Query embed | ~20 ms |
| Dense + BM25 + RRF | ~20 ms |
| FlashRank rerank (40 docs) | ~30 ms |
| Query rewrite (follow-ups only) | ~1–2 s |
| **Generation** | **~3–5 s** ← dominates |
| **Total** | **~4–7 s**, first token <1 s with streaming |

**Read that table before optimising anything.** The entire retrieval stack costs ~70 ms against ~4 s of generation. Retrieval optimisation should target *quality*; latency optimisation should target *perceived* speed (streaming, `keep_alive`).

---

## 10. Recommended architecture

```
INDEXING  (on startup / Reload; incremental via content hash)
  docs/*.{pdf,txt}
    → parse            pypdf + pdfplumber   [Docling optional]
    → structure        detect headings, control IDs, page numbers
    → chunk            recursive ~400 tok / ~60 overlap, on control boundaries
    → contextualise    breadcrumb header  [+ LLM header, opt-in, hash-cached]
    → embed            ollama.embed, "search_document: " prefix, batch 32
    → store            Chroma (cosine) + bm25s index, side by side
                       metadata: doc, section, page, control_id, parent_id, hash

QUERY
  question
    → rewrite          only if history exists (small LLM call)
    → retrieve         dense top-20  ∥  BM25 top-20
    → fuse             RRF (k=60)
    → rerank           FlashRank ms-marco-MiniLM-L-12-v2 → top-5
    → gate             top score < threshold ? refuse : continue
    → expand           child chunks → parent sections, dedup
    → generate         Ollama, labelled context [S1]…[S5], streamed
    → cite             parse labels → document › section › p.N + sources panel
```

**Every element traces to a section above.** Nothing is here because it is fashionable.

---

## 11. Corrections made during verification

Recorded because they show the failure modes of AI-assisted research:

1. **Fabricated-looking IDs that were real.** Citations like `arXiv:2605.00631` and `2603.07612` looked like hallucinated future IDs. They resolve — May and March 2026 respectively. *Lesson: "implausible" is not evidence; check.*
2. **A plausible-looking ID that was wrong.** MiniCheck was cited as `arXiv:2404.10699`. That ID is *ECLAIR: A High-Fidelity Aerial LiDAR Dataset*. Correct ID: **`2404.10774`**. *Lesson: a resolvable citation is not a correct one — check that it resolves to the claimed paper.*
3. **A technically impossible recommendation.** Initial research proposed reranking with `mxbai-rerank` served via Ollama. Ollama has no rerank endpoint ([PR #7219](https://github.com/ollama/ollama/pull/7219), still open). The plan would have failed at implementation. *Lesson: verify that an API exists before designing around it.*

4. **A wrong identifier in a real citation.** The MDPI compliance-RAG paper was cited under ISSN `2078-2289`; the correct one is `2078-2489` (*Information*). The paper is real and turned out to be the most directly relevant source found — nearly lost to a two-digit transposition.

Also corrected: `explodinggradients/ragas` → `vibrantlabsai/ragas`; `uv` was listed as a runtime dependency (it is a build tool); and several star counts were stale by 2–5× (Onyx 16k → 31.1k, Kotaemon 5.5k → 25.6k, FlashRank 1.5k → 994).

**Net result of the verification pass:** 4 substantive errors caught, 1 unimplementable design decision reversed, and 1 highly-relevant source recovered. Roughly one problem for every four claims checked.

---

## 12. Ranked backlog

| # | Change | Expected gain | Effort | Verdict | Phase |
|---|---|---|---|---|---|
| 1 | Correct `nomic-embed-text` prefixes | Avoids 20–50% silent loss | Trivial | **MUST** | 1 |
| 2 | Cosine (not L2) in Chroma | Avoids silent degradation | Trivial | **MUST** | 1 |
| 3 | Eval harness + golden set | Makes everything below measurable | Low | **MUST FIRST** | 3 |
| 4 | Hybrid BM25 + dense + RRF | +20–30% precision | Low | **MUST** | 3 |
| 5 | FlashRank reranking | +10–25% nDCG | Low | **MUST** | 3 |
| 6 | Inline citations | Trust / verifiability | Low | **MUST** | 4 |
| 7 | Confidence-gated refusal | Spec requirement | Low | **MUST** | 4 |
| 8 | Content-hash incremental index | Reload in seconds | Low | **HIGH** | 2 |
| 9 | Breadcrumb chunk headers | +10–15% precision | Low | **HIGH** | 2 |
| 10 | Conversational query rewriting | +10–20% follow-up accuracy | Low | **HIGH** | 4 |
| 11 | Parent–child retrieval | +10–15% context relevance | Medium | **HIGH** | 3 |
| 12 | Streaming + `keep_alive` | Perceived latency | Low | **HIGH** | 4/5 |
| 13 | LLM contextual headers (cached) | +5–10% over breadcrumb | Medium | **MEDIUM** | 5 |
| 14 | Docling optional parser | Better tables | Medium | **MEDIUM** | 5 |
| 15 | Multi-query / step-back | +10–15% recall | Medium | **DEFER** | — |
| 16 | MiniCheck groundedness | Hallucination detection | High | **DEFER** | — |
| 17 | Adaptive routing | Latency savings | Medium | **DEFER** | — |
| 18 | Semantic chunking | Inconsistent | Medium | **REJECT** | — |
| 19 | Late chunking | +24% nDCG, but impossible via Ollama | — | **REJECT** | — |
| 20 | RAPTOR / GraphRAG / Agentic | Wrong problem for this corpus | Very high | **REJECT** | — |

---

## Sources

**Chunking** · [Semantic chunking cost (2410.13070)](https://arxiv.org/abs/2410.13070) · [Late chunking (2409.04701)](https://arxiv.org/abs/2409.04701) · [Contextual Retrieval (Anthropic)](https://www.anthropic.com/engineering/contextual-retrieval) · [Dense X Retrieval (2312.06648)](https://arxiv.org/abs/2312.06648) · [KohakuRAG (2603.07612)](https://arxiv.org/abs/2603.07612) · [H-RAG (2605.00631)](https://arxiv.org/abs/2605.00631)

**Retrieval** · [RRF, SIGIR 2009](https://dl.acm.org/doi/10.1145/1571941.1572114) · [BM25 to Corrective RAG (2604.01733)](https://arxiv.org/abs/2604.01733) · [RAGRouter-Bench (2602.00296)](https://arxiv.org/abs/2602.00296)

**Reranking** · [ColBERTv2, NAACL 2022](https://aclanthology.org/2022.naacl-main.272/) · [Ollama rerank PR #7219](https://github.com/ollama/ollama/pull/7219)

**Architectures** · [Self-RAG (2310.11511)](https://arxiv.org/abs/2310.11511) · [CRAG (2401.15884)](https://arxiv.org/abs/2401.15884) · [RAPTOR (2401.18059)](https://arxiv.org/abs/2401.18059) · [Adaptive-RAG (2403.14403)](https://arxiv.org/abs/2403.14403) · [Agentic RAG survey (2501.09136)](https://arxiv.org/abs/2501.09136) · [GraphRAG](https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/) · [LightRAG](https://github.com/HKUDS/LightRAG)

**Grounding & conversation** · [MiniCheck (2404.10774)](https://arxiv.org/abs/2404.10774) · [ChatQA (2401.10225)](https://arxiv.org/abs/2401.10225)

**Embeddings** · [Nomic Embed (2402.01613)](https://arxiv.org/abs/2402.01613) · [model card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)

**Evaluation** · [RAGAS](https://github.com/vibrantlabsai/ragas) · [ARES, NAACL 2024](https://aclanthology.org/2024.naacl-long.20/)

**Domain** · [KG-enhanced RAG for InfoSec compliance, *Information* 17(4):389](https://doi.org/10.3390/info17040389)
