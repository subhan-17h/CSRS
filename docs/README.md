# docs/ — the corpus

Everything CSRS can answer questions about lives here. Drop a supported file in
(`.pdf` or `.txt`), press **Restart & Reload Documents** in the app, and it becomes
queryable. No code change is required to add a standard.

## Getting the corpus

```bash
python scripts/fetch_docs.py       # stdlib only; works before `uv sync`
```

Most of this directory is **not** committed. The standards are downloaded on demand,
because some are large and some are not ours to redistribute.

## What ships in the repo

| File | Why it's committed |
|---|---|
| `samples/NIST_CSF_2.0.txt` | Public-domain sample so a fresh clone is queryable immediately, with no download. Text extracted from the official CSF 2.0 PDF; running headers removed, nothing else changed. |

## What the fetch script downloads

| Standard | File | Source | Licence |
|---|---|---|---|
| NIST Cybersecurity Framework (CSF) 2.0 | `NIST.CSWP.29_CSF-2.0.pdf` | [nvlpubs.nist.gov](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf) | US Government work — **public domain** (17 U.S.C. 105) |
| NIST SP 800-53 Rev. 5 | `NIST.SP.800-53r5.pdf` | [nvlpubs.nist.gov](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf) | US Government work — **public domain** |
| NIST SP 1299 (CSF 2.0 Quick-Start Guide) | `NIST.SP.1299.pdf` | [nvlpubs.nist.gov](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1299.pdf) | US Government work — **public domain** |
| OWASP Top 10:2021 | `OWASP_Top_10_2021.txt` | [owasp.org/Top10](https://owasp.org/Top10/) · [github.com/OWASP/Top10](https://github.com/OWASP/Top10) | **CC BY 4.0** © OWASP Foundation |

The OWASP Top 10 is published as MkDocs markdown rather than a PDF, so the script
assembles the official English sources into a single TXT in reading order. The content
is unmodified; a provenance and attribution header is prepended, as CC BY 4.0 requires.

## What is deliberately *not* here

**CIS Controls v8.1** — free of charge, but CIS requires registration and its terms
restrict redistribution. The fetch script does not download it and the repo never
commits it. If you want it, download it from
[cisecurity.org/controls](https://www.cisecurity.org/controls) and drop the PDF into
this directory; it will be picked up like any other document.

**ISO/IEC 27001:2022** — copyrighted and sold by ISO (~£220). `CSRS.md` lists it as an
example standard, but shipping it would be copyright infringement, so it is **excluded**.
This is a licensing decision, not a technical limitation: if you hold a licensed copy,
place the PDF in this directory and it works exactly like the others. That is the
extensibility requirement doing its job.

## A note on file sizes

`NIST.SP.800-53r5.pdf` is 492 pages and is the corpus's stress test — dense control
tables, heavy cross-referencing. Expect the first index of it to take a while; after
that, content-hash caching means unchanged files are skipped on reload.
