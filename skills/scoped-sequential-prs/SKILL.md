---
name: scoped-sequential-prs
description: Use when splitting a large or messy change into an ordered series of clean, single-purpose PRs — reconstructing history into staged PRs, keeping each PR strictly in scope, or preventing later-phase code and prose from leaking into an earlier PR.
---

# scoped-sequential-prs

## Overview

Turn one big or tangled body of work into a sequence of PRs, each with a single purpose, built in order (PR1 → PR2 → …), each in its own worktree. The discipline that makes it work: **strict scope isolation** — a PR contains only what its stage owns, with no forward references to code or docs that belong to a later PR. A mechanical **contamination check** enforces it.

## When to Use

- Reconstructing a codebase or feature into a clean, ordered PR series from a plan (e.g. `RECONSTRUCTION-PLAN.md`).
- A change is too large to review as one PR and splits along clear seams.
- You catch later-phase files or mentions bleeding into an early PR.

When NOT to use:
- A genuinely atomic change — don't shard it artificially.
- Small change that's one reviewable PR already.

## Workflow

1. **Plan the stages.** Write an ordered list: each PR's name, scope (which files/concerns it owns), and an acceptance checklist. This is the source of truth.
2. **One worktree per PR** so stages don't collide. See superpowers:using-git-worktrees.
3. **Build the PR** touching only files in its declared scope.
4. **Run the contamination check** (below) before opening the PR.
5. **Open the PR**, get it merged, then base the next stage on the new tip.

## The contamination gate

Fail the PR if any changed file falls outside the stage's declared scope:

```bash
# Files changed between the stage's base and its tip
git diff --name-only "$BASE".."$TIP" \
  | grep -Ev '^(packages/parser/|tests/parser/)' \
  && echo "CONTAMINATION: out-of-scope files above" && exit 1 \
  || echo "scope clean"
```

Adjust the `grep -Ev` allow-pattern per stage. Anything printed = a file the stage doesn't own → move it to the PR that owns it. Also scan prose: no PR should *mention* features introduced by a later PR.

## Scope isolation rules

- **No forward-looking code.** PR2 must not import, stub, or reference what PR4 introduces.
- **No forward-looking prose.** Docs/comments in an early PR describe only what exists by that PR.
- **Each PR stands alone** — it builds, tests pass, and it makes sense without the not-yet-merged stages.
- **Shared prerequisite? Pull it earlier.** If two stages need something, it belongs in the earliest stage that needs it, not duplicated.

## Common Mistakes

- **Skipping the diff gate** because the change "feels" scoped — run it; it catches stray files every time.
- **Checking out shared `main` in the primary clone** for a stage — use a throwaway worktree; keep the shared checkout clean.
- **Prose contamination** — code is scoped but a README/comment references a future stage. Grep prose too.
- **Rebasing the whole chain after each merge** — instead, base each stage on the merged tip of the previous one.

**REQUIRED BACKGROUND:** superpowers:using-git-worktrees (isolation per stage) · pairs with fork-pr-flow (targeting each PR) and verify-then-commit (green before each PR).
