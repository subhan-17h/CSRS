# ENGINEERING.md — how CSRS was built, and why

[README.md](README.md) is how to run it. This is the reasoning: the decisions that shaped the
system, the measurements that drove them, and the places where measuring changed the plan.

Every number here was measured on this corpus. Where a measurement contradicted an
assumption, the contradiction is recorded rather than tidied away — those are the parts worth
reading.

---

## The shape of the problem

A RAG system is easy to assemble and hard to make honest. The assembly is four library calls:
parse, chunk, embed, retrieve. The engineering is everything that decides whether the chunk
reaching the model is the *right* chunk, and whether the model says "I don't know" when it
isn't.

Three constraints shaped the build:

1. **Fully offline.** No cloud API. Every model runs locally through Ollama, which caps model
   capability at ~3B parameters on a laptop. A 3B model is far more prone to confabulating
   than a frontier model, so grounding cannot be delegated to the model's good judgement.
2. **Extensible to unseen standards.** The specification asks that a new standard work by
   dropping a file into `docs/`. That is a much stronger requirement than it looks: it rules
   out anything tuned to the documents on hand.
3. **Standards are structurally weird.** SP 800-53 is 492 pages of dense control tables where
   the identifier (`AC-2`, `GV.OC-01`) *is* the semantics. Losing `AC-2` from a chunk's
   metadata loses the ability to answer "what does AC-2 require".

The build was staged so that a working end-to-end answer came early (Phase 1) and everything
after improved a system that already ran. That ordering is why the walking skeleton uses a
naive chunker: it made the first real failure visible in week one instead of week three.

---

## Decision 1 — Replace the regex parser with a layout model

**This is the decision the project turns on, and it came from a lesson rather than a plan.**

The original PDF parser used `pypdf` plus hand-written rules to strip page furniture. It
worked. It also needed **four separate rounds** of increasingly specific heuristics, and each
round was only discovered by testing against a document the previous round had never seen:

| Round | What broke | The fix |
|---|---|---|
| 1 | Running header survived on CSF | Strip repeated lines |
| 2 | NIST's header block is *four* lines deep, not three | Widen the window to 5 |
| 3 | `CHAPTER THREE PAGE 19` changes every page, so exact matching never counted it | Digit-masked signature |
| 4 | Chapter-scoped footers never reach a document-wide majority | Fixed-slot + distinct-number rule |

Rounds 3 and 4 alone were the difference between 490 pages of surviving boilerplate and 0.
Every rule was correct. That is what makes the pattern worth naming: **four rounds of
corpus-tuned rules, each fixing a real defect found only on a document the last round hadn't
seen, is not a debugging streak — it is the signal that the approach doesn't generalise.**
And "doesn't generalise" is a direct violation of constraint 2 above.

So the tool changed. [Docling](https://github.com/docling-project/docling) runs a DocLayNet
layout model that classifies `Page-header`, `Page-footer` and `Section-header` *structurally*,
which suppresses furniture by construction instead of by rule.

**The spike, run before any code was written:**

| Question | Answer |
|---|---|
| Does it suppress furniture structurally? | Yes — **1937 items** (982 headers, 955 footers) classified into `FURNITURE` on SP 800-53 |
| Does every item keep a page number? | Yes — **0 items** lacking page provenance |
| Can page-level citation survive? | Yes — one `export_to_markdown(page_break_placeholder=...)` pass splits into exactly `len(doc.pages)` segments, byte-identical to per-page exports |
| Are tables better? | Yes — real Markdown tables with headers, versus flat pipe rows |
| Speed | **1.99 pages/s** — SP 800-53's 492 pages in 246.8 s |

Both strings that took four rounds of heuristics to kill are absent from Docling's body
output **with no rule written for either**.

The known CSF defect is the satisfying part. A breadcrumb bug had been traced to a line the
regex read as a numbered heading: `1.1 Subcategories that were relocated in CSF 2.0.` It
turned out not to be a caption at all — it is a *wrapped sentence*
(`...gaps in numbering indicate CSF 1.1 Subcategories that were relocated in CSF 2.0.`).
Docling reflows the paragraph, so the line the regex tripped on **stops existing**. That is
the difference between fixing a symptom and removing its cause.

**The cost was accepted with eyes open.** Docling is roughly 5x slower than `pypdf` (1.99 vs
9.5 pages/s), turning a 52-second index into a five-minute one, plus 1.3 GB of weights. Two
things made that affordable: content-hash incremental indexing (Decision 3), which means the
cost is paid once rather than per launch, and a progress UI. `pypdf` remains selectable via
`CSRS_PDF_PARSER=pypdf` as an emergency path that degrades honestly.

> **Transferable lesson.** Rule count is a signal. When each new document needs a new rule,
> the next document will too. Reach for a structural tool rather than writing rule five.
> Recorded as L-4 in [tasks/lessons.md](tasks/lessons.md).

---

## Decision 2 — Take heading depth from what a heading *is*

The migration plan assumed collapsing the chunker's heading layer would be a *deletion* —
Docling emits real Markdown headings, so the hand-rolled patterns could go. That assumption
came from CSF, a 32-page document. Measuring SP 800-53's actual Markdown broke it:

| Measured on Docling's SP 800-53 output | Count |
|---|---|
| Total headings, **all at flat `##`** | 1075 |
| Controls, `## AC-2 ACCOUNT MANAGEMENT` | 322 |
| Enhancements, `## (1) TITLE ...` — note: **not** `AC-2(1)` | 303 |
| Generic field labels, `## Control:` / `## Control Enhancements:` | 274 |

Three consequences, none of them visible without measuring:

1. **Markdown depth is useless for hierarchy.** Every heading is `##`, so deriving depth from
   the marker makes each heading pop the previous one off the stack.
2. **Field labels must not reset control context.** `## Control:` immediately follows
   `## AC-2 ACCOUNT MANAGEMENT`. Treated as a sibling, every chunk of AC-2's actual
   requirement text gets the breadcrumb `... > Control:` and loses `AC-2` entirely.
3. **Enhancements carry no parent.** `## (1) ACCOUNT MANAGEMENT | AUTOMATED...` needs the
   enclosing control from the heading stack to become `AC-2(1)`.

So depth is taken from **what the heading is** — control, enhancement, or section — not from
how many `#` characters precede it.

### The silent regression this caught

The most valuable measurement in the project cost one line of throwaway code:

```
_match_heading("## AC-2 ACCOUNT MANAGEMENT") -> (2, 'AC-2 ACCOUNT MANAGEMENT', None)
_match_heading("AC-2 ACCOUNT MANAGEMENT")    -> (4, 'AC-2 ACCOUNT MANAGEMENT', 'AC-2')
```

Docling emits control headings as real Markdown, so the ATX pattern matched **first** and
returned `control_id=None`. Run over the real corpus, `control_id` coverage collapsed from
**92.1% to 0.0%**.

**Nothing failed.** No exception, no test went red, and the breadcrumbs still looked correct
by eye. Exact-ID retrieval had simply lost its metadata. A test suite cannot catch this,
because every test still passed — which is precisely why the acceptance criterion for that
step was set as a *measured coverage number on the real corpus*, not a passing suite.

Final state after fixing the match order: **1670/1853 = 90.1%**.

That 90.1% is lower than the regex parser's 92.1%, and it is **not** a regression. All 183
chunks without a `control_id` are content that legitimately has no control to attribute:
Errata (67), Table of Contents (20), `Executive Summary`, `INTRODUCTION`. The two figures are
also over different chunk populations (1853 Docling chunks vs 1820 `pypdf` chunks), so they
were never directly comparable. 90.1% is the correct ceiling for this corpus, not a number to
chase.

### One regression accepted deliberately

The old breadcrumb read `... > ACCESS CONTROL > AC-2 ACCOUNT MANAGEMENT`. That family name
came from SP 800-53's *running page header* — which Docling correctly classifies as furniture
and drops. It appears 42 times in the document and **never** as a heading.

It could be restored with a 20-entry `AC -> ACCESS CONTROL` lookup table. That was rejected:
it is exactly the corpus-tuned hardcoding Decision 1 exists to eliminate, and there is no
evidence family-level breadcrumbs affect retrieval. The rule is measure first. Without an
eval harness (see [What isn't built](#what-isnt-built)), that evidence doesn't exist — so the
map stays unwritten.

---

## Decision 3 — Hash bytes, and short-circuit before parsing

Incremental indexing began as a convenience. Decision 1 made it load-bearing: at five minutes
per full index, a "Restart & Reload" button that re-embeds everything is unusable.

The design constraint is about **call order**, not caching. The hash must be taken on the
source file's *bytes* and checked **before `parse()` is invoked**. Hashing chunks — or
hashing after parsing — still pays the entire Docling cost on every run.

That is also why a passing test suite could not verify it: a test cannot distinguish "skipped
before parsing" from "parsed, then discarded". So the proof sabotaged the parser to raise on
the second run:

| Run | Result |
|---|---|
| 1 — cold index | **309.2 s**, 4 documents, 2506 chunks |
| 2 — unchanged, `parse()` rigged to raise | **0.057 s**, `skipped=4`, **parse never called** — 5404x |
| 3 — rewrite identical bytes (mtime changes) | `skipped=4`, `updated=0` — content, not mtime |
| 4 — change one file | `updated=1, skipped=3`, 4.3 s |
| 5 — delete a file | `removed=1`, its chunks gone |

Run 3 is the one that matters in practice: hashing modification time instead of content would
make every `git checkout` trigger a five-minute rebuild.

**A card instruction was overridden here.** The plan specified the reload button should
"clear manifest → rebuild", which contradicted its own stated rationale two sections earlier.
Clearing the manifest *is* re-embedding everything — 309 s per press. The primary button now
runs an incremental reindex (which already detects new, changed and deleted files), and a
separately labelled control does the true full rebuild. Following the instruction literally
would have satisfied the specification on paper and produced an unusable button.

---

## Decision 4 — `top_k` is a retrieval pool, not a generation budget

Phase 1 sent every retrieved chunk straight to the model, because there was no reranker to
narrow them. Measuring what that actually cost:

| k | Latency | Context used |
|---|---|---|
| 5 | 5.2 s | 23% of `num_ctx` |
| 10 | 8.9 s | 47% |
| 20 | 15.0 s | **92.4%** |

Two findings. First, the 3-5 s latency predicted during research was correct all along — at
k=5. The system wasn't slow; it was sending four times more context than it needed. Second,
92.4% of an 8192-token window is a **silent** failure waiting: Ollama truncates an
over-long prompt rather than erroring, so the failure mode is a quietly worse answer with no
signal at all.

The root cause was a conflated default. `top_k_dense` (20) means *retrieval candidate pool*;
`rerank_top_n` (5) means *chunks that reach the model*. With no reranker in between, `ask()`
defaulted to the wrong one. Correcting the default, measured live:

| | Latency | Context |
|---|---|---|
| Before (k=20) | 13.3 s | 57.2% |
| After (k=5) | **7.0 s** | **11.6%** |

Roughly **2x faster on nothing but a default**, with five times the headroom. The UI slider is
capped at 20 with the reason recorded in a comment, so the ceiling cannot be raised without
someone reading why it exists.

---

## Decision 5 — One facade, and the UI never crosses it

`pipeline.py` is the only module the Streamlit layer talks to. `app.py` imports no Chroma, no
Ollama, no manifest.

This was tested rather than trusted. When the task card for the model dropdown specified
`ollama.list() → filter → st.selectbox` — which reads as calling Ollama directly from
`app.py` — the boundary won: model listing lives in `generation.py` (which already owns the
client), `Pipeline.model_availability()` exposes it, and the UI consumes only the facade.
`grep -n "ollama" src/csrs/app.py` returns the error-message copy and a `pull` hint, and
nothing else.

The payoff is concrete. Because the boundary holds, `Pipeline` can be driven headlessly — and
every measurement in this document was produced that way, against the same code path the UI
uses. A UI that reached into Chroma directly would have needed a second, divergent path for
testing.

**A trap this closed.** `ollama.list()` reports `llama3.2:latest` and `phi4-mini:latest`,
while the specification names them untagged. A naive set intersection would have reported
**two mandated models as missing** — a dropdown that lies about the system's own state.
Normalisation is shared between the facade and `scripts/warm_models.py` so the two cannot
drift.

---

## What measurement changed

The through-line of this project is that the measurements repeatedly disagreed with
reasonable assumptions.

| Assumption | What measuring showed |
|---|---|
| Collapsing the heading layer is a deletion | Flat `##` on 1075 SP 800-53 headings; it needed a rewrite |
| Migrating parsers is metadata-neutral | `control_id` silently collapsed 92.1% → **0.0%** |
| The stack is slow (19 s/answer) | It was fast at k=5; the default was wrong |
| Docling costs ~6 min (from its own benchmark) | **1.99 pages/s** — 1.5x faster than the vendor's M3 Max figure |
| `max(chunk.page)` is a fine page count | Understates any document whose trailing pages produce no chunks — persist the real count |
| Guard tests pass in-process | `chromadb` caches clients per path, giving **false passes**; guards must run in separate processes |

The last row cost real time. An initial verification of the store's consistency guards
reported a clean pass that was an artefact of the test harness, not the code. Re-running each
guard in its own process was the only way to get a trustworthy answer.

### Verifying page citations with a different library

Page numbers are the system's most load-bearing metadata: an off-by-one would silently
corrupt every citation, and would look completely fine. Trusting Docling to check Docling
proves nothing, so cited pages were re-read with **`pypdf`** — an independent library:

- PDF pages 46 and 47 both contain `AC-2` and `ACCOUNT MANAGEMENT`;
- page 47 contains the automated-mechanisms enhancement text;
- SP 1299 page 2 contains all six CSF Function names.

The placeholder-based page split carries **no off-by-one**.

That check also confirmed an earlier decision: citations use the **1-based PDF page
position**, not the printed page number. PDF page 46 of SP 800-53 prints "PAGE 19". The
printed number is what a reader sees, but it's stripped as furniture and doesn't survive
parsing — so citing it would mean citing a number the system can no longer verify.

---

## Where it stands, and what it gets wrong

The Phase 2 checkpoint walked the specification section by section against the running
system: 4 documents, 2506 chunks, 316.0 s cold. All six sections are demonstrable. The UI was
verified by rendering `app.py` through Streamlit's `AppTest` and inspecting the real widget
tree — grepping for `st.selectbox` proves the call exists, not that it renders with the right
options.

**The Phase 1 hallucination is fixed, and the fix is visible.** Early on, *"What does AC-2
require?"* returned an invented sentence with `refused=False` — AC-2 is an SP 800-53 control
and the Phase 1 corpus was OWASP-only, so the model confabulated from adjacent access-control
text. Top retrieval score: **0.5685**. With the full corpus it now returns AC-2's actual
lettered requirements a. through j., including NIST's own `[Assignment: organization-defined
...]` notation, citing page 47 at 0.6726 and page 46 at 0.6707.

**The enhancement hierarchy earns its keep.** *"What must an organization do for automated
system account management?"* retrieves at **0.8420** with `control_id=AC-2(1)`. That ID exists
only because bare `(1)` headings resolve against the nearest stacked control (Decision 2).

### The one failure that survives

*"Explain the Identify function."* answers confidently and **wrongly** — from SP 800-53's
`SI-19 DE-IDENTIFICATION` — with `refused=False`. It was diagnosed, not just recorded:

| Query | Top hit |
|---|---|
| `Explain the Identify function.` | 0.7127 `SI-19 DE-IDENTIFICATION` |
| `Explain the Identify function of the NIST Cybersecurity Framework.` | 0.8082 CSF Abstract, then SP 1299 `IDENTIFY` at 0.8017 |

Retrieval is at fault, not generation — the model was faithful to the context it was handed.
Bare "Identify" collides with `DE-IDENTIFICATION` and `IDENTIFICATION AND AUTHENTICATION`, and
SP 800-53 is 2119 of 2506 chunks, so it dominates the candidate pool. Eleven words of context
move the correct chunks from absent to rank 1-2.

**This is the measurable cost of the one optional requirement not built.** In the
specification, the example questions are a *sequence*: "What are the functions of the NIST
Cybersecurity Framework?" is immediately followed by "Explain the Identify function." The
second is a **follow-up**, and conversational context — marked a bonus — is exactly what
resolves it. The failure appears precisely where the specification predicted it would.

**A finding that invalidates part of the planned fix.** The intended remedy for
confabulation was a retrieval-score confidence gate, calibrated on a band of 0.654-0.684
derived from seven earlier probes. This bad answer scored **0.7127** — *above* that band, and
well above the 0.5685 that would have caught the Phase 1 hallucination. A single scalar
threshold **would not catch this**. Confidently-wrong-but-well-retrieved is a distinct failure
class from nothing-relevant-retrieved, and separating them needs more than one number.

---

## What isn't built

Phases 3-5 were deferred. Stating what that costs, rather than what it saves:

- **No evaluation harness.** No golden set, no Recall@10 / MRR / nDCG. Retrieval quality is
  demonstrated by example, not proven by metric. This is the most significant gap: several
  decisions above are explicitly deferred *pending measurement* that now has no instrument.
- **No hybrid retrieval.** Dense only — no BM25, no reciprocal rank fusion. The "Identify"
  failure is partly a lexical-collision problem, which is the kind BM25 fusion helps with.
- **No reranker.** `rerank_top_n` currently means "chunks retrieved" rather than "chunks
  surviving a rerank". The name is aspirational.
- **No conversational memory** (bonus in the specification) — cost quantified above.
- **No inline citations.** Sources are structured but not interleaved into the answer text.
- **Refusal detection is exact-match**, and a model refusing in its own words reads as having
  answered. Deliberately *not* made fuzzy: a fuzzy matcher would misclassify legitimate
  answers that happen to hedge, which is a worse failure than under-counting refusals.

The dependency list still carries `bm25s`, `PyStemmer` and `flashrank` for this deferred work;
they are declared but unused.

---

## If this continued

In priority order, and the order is the point:

1. **Build the golden set and the metrics harness first.** Everything below is a guess
   without it, and three decisions above are already blocked on it.
2. **Add BM25 + RRF.** Cheapest plausible fix for the "Identify" class of failure, and
   directly measurable once (1) exists.
3. **Add the reranker**, which the measurements in Decision 4 suggest is a latency win as much
   as a quality one — narrowing 20 candidates to 5 recovers ~2x while *improving* selection.
4. **Conversational context**, which converts the known failure into a passing question.
5. **Revisit the confidence gate** with the evidence above: one threshold is provably
   insufficient, so it likely needs a score *distribution* signal (top-score margin over the
   pool) rather than an absolute cutoff.

Notably, the two most valuable next steps are both measurement rather than features. That is
the same lesson as Decision 1, arriving from the other direction.
