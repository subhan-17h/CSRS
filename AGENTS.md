# AGENTS.md

This file provides guidance to CODEX AGENT when working with code in this repository.

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

### Keep tasks/todo.md current -- every task, every time

`tasks/todo.md` is the live status of the build and must never go stale. It tracks the
roadmap tasks in [ROADMAP.md](ROADMAP.md) (`T-1.4`, `T-2.1`, ...).

- **Before you start:** confirm the task you were given has an entry. If it does not,
  add one.
- **When its "Done when" is demonstrated:** tick the checkbox `- [ ]` -> `- [x]` in the
  same change as the code. Never tick it on intent -- only on demonstrated behaviour.
- **If you discover something that changes a later task** (a wrong assumption, a library
  trap, a missing prerequisite), add a one-line note under that task so the next agent
  inherits it instead of rediscovering it.
- `tasks/todo.md` is therefore ALWAYS an allowed file to edit, even when the task brief
  names a narrower set of files.

## Working constraints in this repository

- **ASCII only in Python source.** No em dashes, smart quotes or unicode arrows; use
  `->`. Markdown files may use non-ASCII.
- **Never run `git commit`.** Claude reviews every change and owns the commit. Leaving
  changes unstaged or staged is fine; committing is not.
- **Never add attribution or tooling trailers** to any message or file.
- Line length 100. Ruff lint rules `E`, `F`, `I`, `UP`, `B`; `uv run ruff check .` must
  pass clean before you report done.
- `uv` may fail if it tries to initialise a cache under a read-only `~/.cache`. If so,
  prefix commands with `UV_CACHE_DIR=/private/tmp/csrs-uv-cache`.
- Verify with a check that could actually fail. `grep -n '[^\x00-\x7F]'` does **not**
  detect non-ASCII on macOS; use a byte-level `.decode("ascii")` instead. See
  [tasks/lessons.md](tasks/lessons.md) L-2.


## Core Principles

- Simplicity First: Make every change as simple as possible. Impact minimal code.
- No Laziness: Find root causes. No temporary fixes. Senior developer standards.
- Minimal Impact: Only touch what's necessary. No side effects with new bugs.