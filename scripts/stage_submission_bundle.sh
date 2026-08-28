#!/usr/bin/env bash
# Stage the instructor submission bundle at ~/Projects/work/CIL/submission_bundle.
#
# Rebuilds the folder from scratch every run, so it always reflects the current
# deliverables. Build the two PDFs and export the PowerPoint first:
#
#     ./latex/build.sh --slides
#     python scripts/export_pdf_to_pptx.py CSRS_Presentation.pdf CSRS_Presentation.pptx
#
# Restricted sources are deliberately excluded and the script refuses to finish
# if any of them, or an API key, reaches the staging directory. See
# project-docs/SUBMISSION_BUNDLE_README.md for what is excluded and why.
set -euo pipefail

CSRS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CIL="$(dirname "$CSRS")"
OUT="$CIL/submission_bundle"

rm -rf "$OUT"
mkdir -p "$OUT"/{01_report,02_presentation,03_deliverables,04_run_snapshots}
mkdir -p "$OUT"/{05_evaluation,06_figures/charts,06_figures/screenshots,07_archived_v1_v2,08_scripts}

cp "$CSRS/project-docs/SUBMISSION_BUNDLE_README.md" "$OUT/00_README.md"
cp "$CSRS/project-docs/SUBMISSION_EMAIL.md"         "$OUT/EMAIL_DRAFT.md"

missing=0
for artifact in CSRS_Work_Record.pdf CSRS_Presentation.pdf CSRS_Presentation.pptx; do
  if [ -f "$CSRS/$artifact" ]; then
    case "$artifact" in
      CSRS_Work_Record.pdf) cp "$CSRS/$artifact" "$OUT/01_report/" ;;
      *)                    cp "$CSRS/$artifact" "$OUT/02_presentation/" ;;
    esac
  else
    echo "WARNING: $artifact missing -- build the final report and presentation" >&2
    missing=1
  fi
done
[ "$missing" -eq 0 ] || exit 1
cp "$CSRS/RAG_Evaluation_Report.pdf"            "$OUT/01_report/"
cp "$CSRS/project-docs/PROJECT_WORK_HISTORY.md" "$OUT/01_report/"
cp "$CSRS/project-docs/DAY_INDEX.md"            "$OUT/01_report/"

cp "$CIL/alert_rankings_rag.json"     "$OUT/03_deliverables/"
cp "$CIL/alert_ranking_rag_report.md" "$OUT/03_deliverables/"
cp "$CIL/alert_sample_50.json"        "$OUT/03_deliverables/"
cp "$CIL/cretria.md"                  "$OUT/03_deliverables/severity_criteria.md"
cp "$CSRS/results.md"                 "$OUT/03_deliverables/"

cp "$CIL/alert_rag_run.jsonl"      "$OUT/04_run_snapshots/"
cp "$CIL/alert_judge_run.jsonl"    "$OUT/04_run_snapshots/"
cp "$CIL"/parsed_alert_rag_*.json  "$OUT/04_run_snapshots/"
cp "$CIL"/session_alert_rag_*.json "$OUT/04_run_snapshots/"

cp -R "$CSRS/eval/final/." "$OUT/05_evaluation/"
cp "$CSRS"/latex/figures/*.pdf      "$OUT/06_figures/charts/"
cp "$CSRS"/latex/figures/*.png      "$OUT/06_figures/screenshots/"
cp "$CSRS"/assets/screenshots/*.png "$OUT/06_figures/screenshots/"
cp "$CSRS/assets/architecture.svg"  "$OUT/06_figures/"
cp -R "$CIL/archived/." "$OUT/07_archived_v1_v2/"

for f in fetch_docs.py fetch_snort_community_rules.py fetch_snort_rule_docs.py \
         build_snort_rule_docs.py run_alert_rag.py judge_alert_rankings.py \
         build_alert_rag_report.py groq_llm.py warm_models.py; do
  cp "$CSRS/scripts/$f" "$OUT/08_scripts/"
done

# Nothing licensed, copyrighted or secret may leave this machine.
fail=0
while IFS= read -r hit; do
  echo "REFUSING TO SHIP: $hit" >&2
  fail=1
done < <(find "$OUT" \( -name '.env' -o -name '*.env' -o -name 'snort_rule_*.txt' \
           -o -name 'rule_docs_preprocessed_by_sid.json' -o -name 'ISO_IEC*' \
           -o -name 'NIST.SP.800-53r5.pdf' \))
if grep -rqI 'gsk_' "$OUT" 2>/dev/null; then
  echo "REFUSING TO SHIP: an API key appears in the bundle" >&2
  fail=1
fi
[ "$fail" -eq 0 ] || exit 1

echo "staged: $OUT"
du -sh "$OUT" | cut -f1 | xargs echo "size:"
find "$OUT" -type f | wc -l | xargs echo "files:"
