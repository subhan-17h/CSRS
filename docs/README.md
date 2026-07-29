# docs/ — the corpus

Everything CSRS can answer questions about lives here. Drop a supported file in
(`.pdf` or `.txt`), press **Restart & Reload Documents** in the app, and it becomes
queryable. No code change is required to add a standard.

## Getting the corpus

```bash
python scripts/fetch_docs.py       # stdlib only; works before `uv sync`
```

The shipped corpus is intentionally one committed public-domain document.

## What ships in the repo — `docs/samples/`

One standard is committed so a fresh clone is queryable with **no download at all**.

| File | Format | Licence | Why this one |
|---|---|---|---|
| `samples/NIST.CSWP.29_CSF-2.0.pdf` | PDF | US Government work — **public domain** (17 U.S.C. 105) | The spec's headline example standard; answers its example questions about the Framework Functions. Exercises PDF parsing. |

The loaders remain extensible to PDF and TXT documents, but the current production and
evaluation corpus is deliberately restricted to this single CSF source.

## What the fetch script downloads

| Standard | File | Source | Licence |
|---|---|---|---|
| NIST CSF 2.0 | `samples/NIST.CSWP.29_CSF-2.0.pdf` | [nvlpubs.nist.gov](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf) | US Government work — **public domain** |

The command skips the committed sample by default. `--force` atomically refreshes that
same path, so it never creates a duplicate document in `docs/`.

## What is deliberately *not* here

**CIS Controls v8.1** — free of charge, but CIS requires registration and its terms
restrict redistribution. The fetch script does not download it and the repo never
commits it. If you want it, download it from
[cisecurity.org/controls](https://www.cisecurity.org/controls) and drop the PDF into
this directory; it will be picked up like any other document.

**ISO/IEC 27001:2022** — copyrighted and sold by ISO (~£220). `project-docs/CSRS.md` lists it as an
example standard, but shipping it would be copyright infringement, so it is **excluded**.
This is a licensing decision, not a technical limitation: if you hold a licensed copy,
place the PDF in this directory and it works exactly like the others. That is the
extensibility requirement doing its job.

## A note on indexing

The retained CSF source is 32 pages and currently produces 209 chunks. Content-hash
caching skips it on unchanged reloads.
