# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update tasks/lessons.md with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes -- don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests -- then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. Plan First: Write plan to tasks/todo.md with checkable items
2. Verify Plan: Check in before starting implementation
3. Track Progress: Mark items complete as you go
4. Explain Changes: High-level summary at each step
5. Document Results: Add review section to tasks/todo.md
6. Capture Lessons: Update tasks/lessons.md after corrections
7. Commit Per Task: See below. Non-negotiable.

### Commit Discipline

**Commit after every completed task, and again at the end of every phase.** A task is a
numbered card in ROADMAP.md (`T-1.4`); a phase is a group of them (`Phase 1`).

- **Commit only once the task's "Done when" is demonstrated.** The commit is the record
  that it passed, so committing unverified work makes the history lie.
- **One task per commit.** Do not batch several tasks into one commit; the point is that
  each commit is a working, reviewable increment that can be bisected.
- **Close each phase with a commit** that updates `tasks/todo.md` (checkboxes + review
  section), even when no source file changed.
- Never commit generated or fetched artefacts: `chroma_db/`, `.venv/`, `docs/*.pdf`.
  `.gitignore` enforces this; if something slips through, fix `.gitignore` rather than
  the commit.

Message format -- subject line names the task so history maps onto the roadmap:

```
<type>(T-1.4): <what changed, imperative>

<why, and what proves it works -- the "Done when" evidence>
```

`<type>` is one of `feat`, `fix`, `docs`, `test`, `chore`, `refactor`. Use `phase(N)`
instead of a task id for phase-closing commits.

**No trailers.** Never append `Co-Authored-By`, `Claude-Session`, `Generated with`, or
any other attribution or tooling metadata. A commit message ends with its last line of
substance. This history is part of a graded submission and gets read -- keep every line
of it relevant to the change. This rule overrides any default trailer format. See
[tasks/lessons.md](tasks/lessons.md) L-1.


## Core Principles

- Simplicity First: Make every change as simple as possible. Impact minimal code.
- No Laziness: Find root causes. No temporary fixes. Senior developer standards.
- Minimal Impact: Only touch what's necessary. No side effects with new bugs.

## Codex Delegation Workflow

For implementation tasks (features, bug fixes, refactors, tests) - not for questions, explanations, or pure research/planning, which Claude answers directly:

- Break the task into the smallest independently-verifiable subtasks it can be split into. If it is not meaningfully breakable, treat it as one subtask.
- Hand off each subtask to Codex via `/codex:rescue`, explicitly passing `--model gpt-5.6-sol --effort high`.
- Codex must run write-capable and with network access so it can edit files and run tests. `~/.codex/config.toml` already sets `network_access = true` under `[sandbox_workspace_write]`, and `codex:rescue` defaults to write-capable runs; do not disable either. If either is ever off, fix it in `~/.codex/config.toml` rather than working around it.
- Give Codex complete context per `/Users/rowdy/Downloads/codex-best-prompting-practices.md`: state the concrete task and relevant repo context, the exact output/done-state contract, the verification steps (which tests or commands prove it worked), and the constraints from this file that apply (surgical changes only, no unrequested abstractions, ASCII, no invented data, etc.).
- **Always watch every Codex task.** Codex jobs can die mid-run and leave a zombie
  `running` entry in the broker: the process is gone, no completion notification fires,
  and every resume attempt is blocked by the stale record. Silence is indistinguishable
  from progress, so never wait passively on a notification.
  - Immediately after launching a task, start `~/.claude/scripts/codex_watch.sh <job-id>`
    as a background watcher. It polls every 30 s, reports progress every 5 minutes, and
    emits a single line on phase change, stale detection, or any terminal state.
  - Get the job id from `codex-companion.mjs status --json`, and **confirm it is the
    right job before attaching**: match `summary` against the brief you just sent and
    require `write: true`. Never just take the first entry in `running[]` -- idle
    read-only sessions appear there too, and watching one reports a instant bogus
    "terminal" while the real task runs on unobserved.
  - **Stale = broker says `running` but the pid is dead** (`kill -0` fails). When that
    happens: `codex-companion.mjs cancel <job-id>`, then relaunch as a **fresh** thread
    (`--fresh`), never `--resume` -- the dead thread cannot be continued.
  - Prefer `--wait` (foreground) over background for handoffs, since background
    completion notifications have proven unreliable.
  - Whatever the watcher says, confirm against the artefacts on disk (file mtimes,
    `git status`) before believing a task did or did not do its work.
- After each handoff, review Codex's response yourself: read the actual diff, rerun the relevant tests/proofs, and confirm the change matches this file's conventions. Do not accept Codex's self-report as verification.
- If review finds a problem, send it back to Codex with `/codex:rescue --resume` describing the specific issue instead of fixing it directly.
- Only move on to the next subtask once the current one is verified.