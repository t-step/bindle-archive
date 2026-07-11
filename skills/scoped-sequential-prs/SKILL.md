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

1. **Plan the stages.** Write an ordered list: each PR's name, scope (which files/concerns it owns), and an acceptance checklist. This is the source of truth. No written plan? State the current stage's one-line purpose explicitly before building (e.g. "PR1: signup input validation") — step 3 of the contamination gate checks the declared scope against this line.
2. **One worktree per PR** so stages don't collide. See superpowers:using-git-worktrees.
3. **Build the PR** touching only files in its declared scope.
4. **Run the contamination check** (below) before opening the PR.
5. **Open the PR**, get it merged, then base the next stage on the new tip.

## The contamination gate

The gate has **three steps**; the PR passes only if all three do. Step 1
catches out-of-scope *files*; step 2 catches forward references smuggled
*inside* in-scope files (an import or call into a later stage passes step 1
— and can ship a PR that doesn't even build); step 3 catches a scope that
was quietly widened to make steps 1 and 2 pass.

```bash
# Step 1 — file scope: every changed file must be one the stage owns
git diff --name-only "$BASE".."$TIP" \
  | grep -Ev '^(packages/parser/|tests/parser/)' \
  && echo "CONTAMINATION: out-of-scope files above" && exit 1 \
  || echo "file scope clean"

# Step 2 — content scan: no added line may reference later-stage code
git diff -U0 "$BASE".."$TIP" \
  | grep '^+' | grep -v '^+++' \
  | grep -nE 'evaluator|evaluate' \
  && echo "CONTAMINATION: forward references above" && exit 1 \
  || echo "content clean"

# Step 3 — scope-declaration integrity: does the declared scope match the
# stage's own purpose? (Judgment check, not mechanical.)
#
# First, a concrete check: does any file step 1's pattern allows carry its
# own marker — a header, comment, docstring, or plan entry — naming a
# *different* stage (e.g. "PR2:", "TODO(later stage)", "not yet built out")?
# A file that marks itself as later-stage work is a SCOPE OVERRIDE the
# moment it's included, full stop — do not reason your way to "it still
# matches this stage's purpose." Declare it (below) instead.
#
# Then, for every remaining file step 1's pattern allows, and every symbol
# step 2's pattern excludes: does it trace to the stage's one-line purpose
# (or the plan, if one exists)? If yes, done.
#
# If no — a later-stage file/symbol was pulled in for a reason other than
# "this is what the stage is" — that's also a SCOPE OVERRIDE, not a clean PR.
# State every override found explicitly, in the PR description and the gate
# report:
#   Scope override: <file/symbol> — <why, e.g. an explicit user instruction>
#
# A scope override isn't automatically wrong. It must never be silently
# absorbed into the step 1/2 patterns and reported as plain "clean" —
# including by re-justifying a marked-later-stage file as "part of this
# stage's purpose after all." Do not report "scope clean" unless step 3
# found no override needed, or every override found is stated above.
```

Adjust all three checks per stage: the `grep -Ev` allow-pattern is the files this
stage owns; the step-2 pattern is the module names and key identifiers owned by
*later* stages (take them from the plan); step 3 has no pattern — it's a check
against the stage's own stated purpose. Anything step 1 prints = a file the
stage doesn't own → move it to the PR that owns it. Anything step 2 prints = a
forward reference → strip it from this PR (it belongs in the stage that
introduces it). Anything step 3 finds = an undeclared scope widening → state it
as a `Scope override:` line, don't quietly redefine the allow-pattern to hide
it. The gate's output is the verdict — do not report "scope clean" unless all
three steps passed (or every step-3 finding is declared). Also scan prose: no
PR should *mention* features introduced by a later PR.

## Scope isolation rules

- **No forward-looking code.** PR2 must not import, stub, or reference what PR4 introduces.
- **No forward-looking prose.** Docs/comments in an early PR describe only what exists by that PR.
- **Each PR stands alone** — it builds, tests pass, and it makes sense without the not-yet-merged stages.
- **Shared prerequisite? Pull it earlier.** If two stages need something, it belongs in the earliest stage that needs it, not duplicated.

## Common Mistakes

- **Skipping the diff gate** because the change "feels" scoped — run it; it catches stray files every time.
- **Quietly widening the allow-pattern to fit what you already built, then reporting clean** — that's a scope override; state it in the PR description and gate report, don't launder it through a self-chosen pattern.
- **Reasoning a later-stage-marked file "actually matches this stage's purpose after all"** — a file's own header/comment naming a different stage (e.g. "PR2: ...") is a scope override the moment it's included, no matter how the purpose-tracing argument goes. Declare it; don't argue it away.
- **Checking out shared `main` in the primary clone** for a stage — use a throwaway worktree; keep the shared checkout clean.
- **Prose contamination** — code is scoped but a README/comment references a future stage. Grep prose too.
- **Rebasing the whole chain after each merge** — instead, base each stage on the merged tip of the previous one.

**REQUIRED BACKGROUND:** superpowers:using-git-worktrees (isolation per stage) · pairs with fork-pr-flow (targeting each PR) and verify-then-commit (green before each PR).
