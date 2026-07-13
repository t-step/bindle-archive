# Design: workflow composition, precedence, and invariant rules

Resolves the design half of issue #31. Status: **approved design, not yet
implemented** — the implementation is `docs/workflow-composition.md` itself
(a doc-sized contract; there is no separate build phase). When an
implementation question isn't answered here, decide it while writing that doc
and fold the answer back into this design, not improvise silently.

## Problem

Bindle now has multiple workflows that can apply to the same task: modes
(`hands-on-keyboard`), task workflows (`fork-pr-flow`, `verify-then-commit`,
`scoped-sequential-prs`, `session-continuity`, `delegated-implementation-packets`,
`delegation-profiles`), a set of standing invariants (`global/CLAUDE.md`), and
two providers that automate the same contract differently (Claude skills vs.
Codex manual docs). Nothing today says what happens when several apply at
once, which one may narrow or relax another, or how a delegated subagent
inherits any of it. Left alone, each new workflow increases the chance of
contradictory or duplicated guidance — already visible in this repo (see
Overlap 3 below).

## Goals

1. A classification model with exactly five categories, each with real
   examples from this repo — no invented workflow to make the model tidy.
2. A single, fixed precedence order and one relaxation rule ("narrow or add,
   never relax, skip, or contradict a higher category") that resolves real
   overlaps without a case-by-case lookup table.
3. A stop-and-ask rule for genuine same-tier contradictions — never silently
   pick a side.
4. A lightweight, already-organic convention for declaring dependencies
   between workflow docs (reference, don't restate) — no new machinery.
5. An inheritance rule for delegated tasks that extends
   `delegation-profiles.md`'s existing "narrow, never widen" rule from
   authority alone to the full five-category stack.
6. At least three real, resolved overlap scenarios, plus classification of
   every workflow this repo currently ships.

## Non-goals

- No workflow execution engine, policy interpreter, or runtime that decides
  precedence programmatically — `product-boundary.md` non-goal 1.
- No automatic selection of "the applicable workflow set" without human or
  provider judgment — this doc's own non-goal list.
- No rewriting of `fork-pr-flow` or any other existing skill to remove
  duplication found while writing this contract (Overlap 3) — that's a
  follow-up, recorded as "Noticed, not done," not actioned here.
- No new provider-adapter mechanism beyond what `provider-interop.md`
  already defines; this contract classifies existing adapters, it doesn't
  add new ones.

## The model

### Categories

| Category | What it is | Real examples in this repo |
|---|---|---|
| Invariants | Rules no other category may relax | `global/CLAUDE.md`: never push unless asked; never `--no-verify`; never commit to `main` on a branch-disciplined repo |
| Project instructions | Repo-local CLAUDE.md/AGENTS.md, or a specific instruction given for this task/session | This repo's root `CLAUDE.md`; an explicit ask like "commit on a branch, open a PR closing #N" |
| Modes | User-selected collaboration behavior | `hands-on-keyboard` |
| Task workflows | Steps for a particular kind of work | `fork-pr-flow`, `verify-then-commit`, `scoped-sequential-prs`, `session-continuity`, `delegated-implementation-packets`, `delegation-profiles` |
| Provider adapters | How a task workflow's steps map onto a specific provider's primitives | A Claude Code skill/command/agent vs. the same contract followed manually from Codex docs (`using-bindle-with-codex.md`) |

An invariant may name its own narrow carve-out in its own text (e.g. "unless
I explicitly ask") — that carve-out is part of the invariant, not an
external override reaching in from a lower category.

### Precedence and the relaxation rule

Fixed order, top to bottom: **invariants → project instructions → modes →
task workflows → provider adapters.**

A lower category may narrow what a higher category permits, or add detail
within the space the higher category leaves open — it may never relax, skip,
or contradict it. A mode changes *how* a task workflow executes (pacing,
checkpoints, who drives); it never changes *what* the workflow requires.

### Contradiction rule

Two same-tier items (or a lower category that appears to genuinely
contradict, not just narrow, a higher one): stop and report the two
conflicting sources by name — never silently pick one. This extends
`delegated-implementation-packets.md`'s rule 1 (repo/remote state outranks
narration) from *state vs. narration* to *contradiction vs. narration*: a
convincing resolution invented on the spot is not a resolution.

### Declaring dependencies

Formalizes a pattern this repo already uses without naming it: packets
"reference, rather than restate" the neighboring contracts they depend on
(`delegated-implementation-packets.md`); skills cite
`**REQUIRED BACKGROUND:** superpowers:test-driven-development`
(`CONTRIBUTING.md`). A workflow doc declares a dependency by naming the other
doc/skill in prose and linking to it — never by copying its substance. No new
schema or machinery.

### Inheritance into delegated tasks

Extends `delegation-profiles.md`'s rule 2 (a sub-delegated worker's authority
is the intersection of its own profile and everything its parent explicitly
granted — narrow, never widen) across the whole stack:

- **Invariants** always inherit in full and cannot be stripped by any
  delegation.
- **Project instructions** inherit unless the delegating task explicitly
  narrows them for the sub-task.
- **Modes** do **not** auto-inherit into a bounded subagent dispatch — the
  human isn't pacing a subagent turn-by-turn — unless the parent explicitly
  passes the mode down.
- **Task workflows** and **provider adapters** inherit only the ones
  relevant to the delegated scope (a Research-profile sub-task that never
  touches git doesn't need `fork-pr-flow` inherited).

## Worked examples (three real overlaps)

### 1. Invariant × explicit instruction

`global/CLAUDE.md`: "Never push... unless I explicitly ask." This session's
#32 work included an explicit instruction: "Commit on a dedicated branch,
open a PR that closes #32." Resolution: the invariant's own carve-out
("unless I explicitly ask") is satisfied by a project-instruction-tier
request naming the exact action. The invariant was never relaxed by a lower
category reaching up — the instruction operated inside the exception the
invariant itself defines.

### 2. Mode × task workflow

`hands-on-keyboard` (mode: user stays hands-on, Claude doesn't quietly finish
work end-to-end) vs. `verify-then-commit` (task workflow: "run tests +
typecheck + lint and commit only if green" — read naively, an autonomous
action). Resolution: the mode changes execution style, not the workflow's
required content. Under `hands-on-keyboard`, the gate's pass/fail criteria
still apply in full, but Claude proposes running it and reviews the result
with the user rather than committing autonomously on green — the task
workflow is narrowed in *how* it executes, never in *what* it checks.

### 3. Duplicated invariant across two docs

`fork-pr-flow`: "Never merge a PR you authored." `delegation-profiles.md`
(#32): merge is a Privileged action, granted only by explicit authorization.
Same invariant, stated twice — one as a task-workflow-level enforcement
line in a Claude-native skill, one as the portable contract's formal
definition. Resolution: classify both as expressions of one invariant;
`delegation-profiles.md` is the canonical definition, `fork-pr-flow` is its
Claude-native trigger. Recorded as a dependency-declaration opportunity
(`fork-pr-flow` could cite `delegation-profiles.md` instead of restating the
rule) — **not edited in this PR**; see Non-goals.

## Where this fits

- [delegation-profiles.md](../delegation-profiles.md) supplies the authority
  ladder this doc's inheritance section extends to the full category stack.
- [delegated-implementation-packets.md](../delegated-implementation-packets.md)
  supplies the "state outranks narration" rule this doc extends to
  contradictions, and is itself a task workflow classified here.
- [provider-interop.md](../provider-interop.md) is the standing contract for
  what "provider adapter" means; this doc classifies existing adapters, it
  doesn't redefine them.
- [product-boundary.md](../product-boundary.md) non-goal 1 (no workflow
  engine) is why this stays a classification-and-precedence doc, not
  automation.
