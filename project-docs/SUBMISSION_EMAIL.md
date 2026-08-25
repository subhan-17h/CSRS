# Email draft — internship final submission

Fill the bracketed placeholders, attach the two PDFs, paste the Drive link, send.

---

**To:** `[instructor email]`
**Cc:** `[programme coordinator, if required]`
**Subject:** Internship final submission — CSRS (Subhan Amir, 21 July – 21 August 2026)

---

Dear `[instructor name]`,

Please find my final internship submission below. It covers the work I carried out between
21 July and 21 August 2026 on CSRS, a local retrieval-augmented generation system for
cybersecurity standards, and the alert-triage experiment I built on top of it.

**1. Final report — day-wise tasks and results**

Attached as `CSRS_Work_Record.pdf`. Section 3 is the day-by-day record: all 32 days of the
period, with the 16 working days numbered and each one's commits, line counts and outcome.
The remaining sections cover what was built, how answer quality was measured, and the alert
experiment. A Markdown version with the complete 117-commit ledger is in the Drive folder as
`PROJECT_WORK_HISTORY.md`.

**2. GitHub repository, finalised day-wise**

https://github.com/subhan-17h/CSRS

The 117 commits are dated and each records one completed task. To read the work a day at a
time:

- `project-docs/DAY_INDEX.md` maps every day to its commits, artefacts and tag.
- Thirteen annotated tags, `day-01-2026-07-21` … `day-16-2026-08-21`, mark each working day
  that produced commits. `git tag -n99 -l 'day-*'` lists them with summaries.
- Three working days (30, 31 July and 3 August) produced data artefacts rather than code, so
  they carry no tag; the day index lists the files that evidence them.

**3. Presentation**

Attached as `CSRS_Presentation.pdf` — 26 slides covering the system, the timeline, the
evaluation, the alert experiment and the limitations.

**4. Google Drive folder — all prepared files**

`[paste Drive link here]`

Contains the reports and slides, the JSON deliverables, the complete run snapshots for every
model call, the 250-row evaluation results, all figures, the archived v1 and v2 runs, and the
scripts that regenerate the corpus. A `00_README.md` at the top explains each folder.

Three source documents are deliberately **not** in the folder: ISO/IEC 27001:2022 is a
licensed document, and the Snort rule documentation is Cisco copyright. The scripts in
`08_scripts/` re-fetch and rebuild both, so every result in the report can still be
reproduced. The vector index is also excluded — it is 162 MB and regenerates from the corpus.

**A note on the results.** The evaluation compared five local models across three independent
metrics over 50 questions; `gemma2:2b` led all three. The alert experiment ran three times.
The final run improved rule identification substantially — 40 of 50 alerts correctly
identified with none wrong, which is exactly the ceiling retrieval allows — but severity
ranking regressed, from 32 exact matches to 29. I have reported this rather than tuning it
away: the report shows the analysis that diagnoses the cause, and names the specific prompt
change that would test it. I thought the honest result and its diagnosis were worth more than
a better number.

I am happy to walk through any part of this or to answer questions.

Kind regards,
Subhan Amir
`[programme / institution]`

---

## Before sending

- [ ] Attach `CSRS_Work_Record.pdf`
- [ ] Attach `CSRS_Presentation.pdf`
- [ ] Upload `submission_bundle/` to Drive and **set sharing so the instructor can open it**
- [ ] Paste the Drive link
- [ ] Replace: instructor email, instructor name, programme/institution
- [ ] Confirm the repository is public, or that the instructor has access
