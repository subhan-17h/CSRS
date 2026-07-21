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
