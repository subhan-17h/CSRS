#!/usr/bin/env bash
# Build the internship work record.
#
#   ./latex/build.sh              compile the .tex only (the usual case)
#   ./latex/build.sh --figures    regenerate the data figures and deliverable
#                                 cards first, then compile
#   ./latex/build.sh --slides     also compile the presentation deck
#   ./latex/build.sh --shots      also re-capture the live UI screenshots; this
#                                 needs the API and Streamlit running, and an
#                                 Ollama chat model installed:
#                                     uv run csrs-api
#                                     uv run streamlit run src/csrs/app.py
#
# Output: CSRS_Work_Record.pdf, and with --slides CSRS_Presentation.pdf, in this
# directory and at the repository root.
set -euo pipefail

slides=0

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"

for arg in "$@"; do
  case "$arg" in
    --figures)
      UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/csrs-uv-cache}" \
        uv run --group eval python "$here/make_figures.py"
      python3 "$here/make_excerpts.py"
      ;;
    --slides)
      slides=1
      ;;
    --shots)
      python3 "$here/make_screenshots.py"
      ;;
    *)
      echo "unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

tectonic -X compile "$here/CSRS_Work_Record.tex" --outdir "$here"
cp "$here/CSRS_Work_Record.pdf" "$root/CSRS_Work_Record.pdf"
echo "built $root/CSRS_Work_Record.pdf"

if [ "$slides" -eq 1 ]; then
  tectonic -X compile "$here/CSRS_Presentation.tex" --outdir "$here"
  cp "$here/CSRS_Presentation.pdf" "$root/CSRS_Presentation.pdf"
  echo "built $root/CSRS_Presentation.pdf"
fi
