# Internship work record (LaTeX)

`CSRS_Work_Record.tex` is the source for the work-record PDF. It is written to be
edited by hand: the style block sits at the top under commented headings, and the
body below it is plain prose, tables and figures in the order they appear.

## Build

```bash
./latex/build.sh              # compile only
./latex/build.sh --figures    # regenerate charts + deliverable cards, then compile
./latex/build.sh --shots      # also re-capture the live UI screenshots
```

The engine is [tectonic](https://tectonic-typesetting.github.io) (XeTeX); it fetches
the packages it needs on first run, so the first build needs a network connection.

## Where the figures come from

| Figure | Produced by | From |
|---|---|---|
| `architecture.pdf` | headless Chrome, once | `assets/architecture.svg` |
| `eval_models.pdf` | `make_figures.py` | `eval/final/summary.csv` |
| `alert_v1_v2.pdf` | `make_figures.py` | the two published run reports |
| `excerpt_report.pdf`, `excerpt_json.pdf` | `make_excerpts.py` | the alert deliverables in `~/Projects/work/CIL/` |
| `ui_*.png` | `make_screenshots.py` | the running application |

`--shots` drives a real browser against a running system, so start both interfaces
first and have an Ollama chat model installed, or the captured answers will be empty:

```bash
uv run csrs-api                        # http://127.0.0.1:8000
uv run streamlit run src/csrs/app.py   # http://localhost:8501
ollama pull gemma2:2b
```

## Editing notes

- Section headings render as a full-width accent band; the definition is the
  `\section` redefinition in the style block.
- Screenshots are wrapped in `proofbox`, which draws the light frame around them.
- Tables use unnumbered captions (`\caption*`) because none are cross-referenced;
  figures are numbered.
- The timeline table is breakable across pages (`ltablex`), so rows can be added
  freely.
