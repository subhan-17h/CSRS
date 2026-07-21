# tasks/lessons.md

Corrections from the user, written as rules so the same mistake isn't repeated.
Reviewed at the start of every session.

---

## L-1 · No attribution trailers in commit messages

**Date:** 2026-07-21 · **Trigger:** the five Phase 0 commits each ended with
`Co-Authored-By: Claude ...` and `Claude-Session: https://...`.

**Rule.** Never append `Co-Authored-By`, `Claude-Session`, `Generated with`, or any
similar attribution or tooling trailer to a commit message. A commit message ends with
its last line of substance.

**Why.** This is a graded submission. The commit history is part of what is read, and
tooling metadata is noise in it — it says nothing about the change and dilutes messages
that are otherwise doing real explanatory work.

**How to apply.** A commit message contains exactly: a `<type>(T-x.y): <imperative>`
subject, a blank line, then a body explaining *why* the change was made and what proves
it works. Nothing after that. This overrides any default or harness-suggested trailer
format — if a default says to add one, do not.

---

## L-2 · Verify claims against reality before recording them as fact

**Date:** 2026-07-21 · **Trigger:** self-observed during Phase 0, kept because it paid
off twice in one phase.

**Rule.** When a planning document asserts something checkable — a model exists, a URL
serves a PDF, a library behaves a certain way — check it before building on it, and
correct the document when it is wrong.

**Why.** Phase 0 alone found two: `gemma4:e2b` was recorded as probably-missing but is
real, and OS_REPOS.md implied an OWASP PDF that has not existed since 2017. Both would
have become confusing failures later.

**How to apply.** Pair every probe with a negative control — the registry check only
meant something because `gemma4:e99b` returned 404. A check that cannot fail proves
nothing.

**Corollary, learned the hard way (T-1.1).** `grep -n '[^\x00-\x7F]' file` does **not**
detect non-ASCII on macOS — BSD grep does not decode `\xNN` inside bracket expressions,
so the pattern silently means something else entirely. The right check is a byte-level
decode: `python -c "Path(p).read_bytes().decode('ascii')"`. The grep gave the correct
answer by accident, which is worse than giving the wrong one. Verify that a verification
actually works.

---

## L-3 · Never wait passively on a Codex task

**Date:** 2026-07-21 · **Trigger:** a T-1.1 handoff appeared stuck for ~20 minutes.

**Rule.** Attach `~/.claude/scripts/codex_watch.sh <job-id>` as a background watcher
immediately after launching any Codex task. Prefer `--wait` for the handoff itself.

**Why.** Codex jobs can die mid-run and leave a zombie `running` entry in the broker —
process gone, no completion notification, and every resume blocked by the stale record.
It happened: the process died at 15:27 having actually completed all its checks, and
nothing surfaced that. Silence is indistinguishable from progress.

**How to apply.** Stale means broker status is `running` but the pid is dead (`kill -0`
fails). Then: cancel the job, relaunch as a **fresh** thread — a dead thread cannot be
resumed. Always confirm against artefacts on disk (file mtimes, `git status`) rather
than trusting any status report, including the watcher's.

**Corollary (T-1.4).** Identify the job before watching it. Taking the first entry of
`running[]` attached the watcher to an idle read-only session (`write: false`), which
reported "terminal" within seconds while the real task ran on unobserved — a false
*success* signal, which is more dangerous than the silence the watcher was built to fix.
Match the job's `summary` against the brief just sent and require `write: true`. The
disk check is what caught it: the watcher said done, and `embeddings.py` did not exist.
