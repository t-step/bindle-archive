# Workflow composition

The provider-neutral contract for **what happens when more than one workflow
applies to the same task** — invariants, project instructions, modes, task
workflows, and provider adapters — and which one yields when they overlap.
Resolves issue [#31](https://github.com/thomas-estep/bindle/issues/31).

Bindle now ships enough workflows that several can apply to one task at
once: a mode the user selected, a task workflow for the kind of work, this
session's own project instructions, and the standing invariants underneath
all of it, automated differently again depending on provider. Nothing said
what happens when several apply at once, which one may narrow or relax
another, or how a delegated subagent inherits any of it. Left alone, each new
workflow increases the chance of contradictory or duplicated guidance —
already visible in this repo (see Overlap 3 below).

This is **not** a workflow execution engine, policy interpreter, or runtime
that decides precedence programmatically —
[product-boundary.md](product-boundary.md) non-goal 1. It is also not
automatic selection of "the applicable workflow set" for a task without human
or provider judgment; deciding which workflows apply stays a human or
provider-config decision. This contract only fixes what happens once that
set is chosen: the order it resolves in, and the rule that keeps a lower
category from silently weakening a higher one.

This doc classifies and orders workflows; it deliberately references, rather
than restates, the neighboring contracts it depends on:

- **What a delegated worker of a given risk level may do** is
  [delegation-profiles.md](delegation-profiles.md)'s ladder (Mechanical,
  Review, Research, Implementation, Privileged), issue #32. The inheritance
  section below extends that contract's "narrow, never widen" rule from
  authority alone to the full five-category stack; it does not redefine the
  ladder itself.
- **What a bounded unit of delegated work looks like** is
  [delegated-implementation-packets.md](delegated-implementation-packets.md).
  A packet *selects* the minimal applicable workflow set for its task; this
  doc defines the precedence a packet's selection has to respect, it does
  not replace the packet contract.
- **What "provider adapter" means** is
  [provider-interop.md](provider-interop.md)'s standing contract for how
  Claude Code and Codex automate the same workflow differently. This doc
  classifies existing adapters as one of its five categories; it does not
  redefine what an adapter is or add new ones.

## The five categories

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

## Precedence and the relaxation rule

Fixed order, top to bottom: **invariants → project instructions → modes →
task workflows → provider adapters.**

A lower category may narrow what a higher category permits, or add detail
within the space the higher category leaves open — it may never relax, skip,
or contradict it. A mode changes *how* a task workflow executes (pacing,
checkpoints, who drives); it never changes *what* the workflow requires.

This is what satisfies #31's acceptance criterion 3, "a workflow cannot
silently weaken an invariant": the relaxation rule above is exactly that
guarantee, stated once as a general rule that applies to every category pair
in the stack, rather than as a per-workflow check that would need
re-deriving every time a new workflow is added.

## Contradiction rule

Two same-tier items (or a lower category that appears to genuinely
contradict, not just narrow, a higher one): stop and report the two
conflicting sources by name — never silently pick one. This extends
[delegated-implementation-packets.md](delegated-implementation-packets.md)'s
rule 1 (repo/remote state outranks agent narration) from *state vs.
narration* to *contradiction vs. narration*: a convincing resolution
invented on the spot is not a resolution.

## Declaring dependencies

Formalizes a pattern this repo already uses without naming it: packets
"reference, rather than restate" the neighboring contracts they depend on
([delegated-implementation-packets.md](delegated-implementation-packets.md));
skills cite `**REQUIRED BACKGROUND:** superpowers:test-driven-development`
([CONTRIBUTING.md](../CONTRIBUTING.md)). A workflow doc declares a dependency
by naming the other doc/skill in prose and linking to it — never by copying
its substance. No new schema or machinery.

## Inheritance into delegated tasks

Extends [delegation-profiles.md](delegation-profiles.md)'s rule 2 (a
sub-delegated worker's authority is the intersection of its own profile and
everything its parent explicitly granted — narrow, never widen) across the
whole stack:

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

This is what satisfies #31's acceptance criterion 4, "delegated agents
receive the relevant inherited constraints": each row above states exactly
what a delegated task keeps, what it can lose, and under what condition.

## Three worked examples

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
rule) — **not edited in this PR**; see the
[design doc](design/2026-07-12-workflow-composition.md)'s non-goals for why
this contract classifies the duplication without rewriting the skill.

This section, together with the two above it, is what satisfies #31's
acceptance criterion 2: at least three realistic overlap scenarios resolved
explicitly.

## Classifying every current workflow

Every skill, command, and provider-neutral contract this repo ships
(`capabilities.json`'s `skill`/`command`/`contract` rows), classified under
the five categories above. This is what satisfies #31's acceptance criterion
1, "existing workflows can be classified under the composition model."

| Name | Type | Category |
|---|---|---|
| `fork-pr-flow` | skill | Task workflow |
| `hands-on-keyboard` | skill | Mode |
| `license-compliance-auditor` | skill | Task workflow |
| `maintain-claude-md` | skill | Task workflow |
| `repo-hygiene-init` | skill | Task workflow |
| `scoped-sequential-prs` | skill | Task workflow |
| `session-continuity` | skill | Task workflow |
| `verify-then-commit` | skill | Task workflow |
| `handoff` | command | Task workflow |
| `license-audit` | command | Task workflow |
| `notes-home` | command | Task workflow |
| `project-profile` | command | Task workflow |
| `promote-insight` | command | Task workflow |
| `session-end` | command | Task workflow |
| `session-start` | command | Task workflow |
| `workflow-review` | command | Task workflow |
| `promote-knowledge` | command | Task workflow |
| `session-notes-format` | contract | Task workflow |
| `hands-on-keyboard-contract` (`docs/hands-on-keyboard.md`) | contract | Mode |
| `delegated-implementation-packets` | contract | Task workflow |
| `delegation-profiles` | contract | Task workflow |
| `capability-inventory` | contract | Task workflow |
| `privacy-boundaries` | contract | Task workflow |
| `knowledge-promotion` | contract | Task workflow |
| `workflow-composition` | contract | Task workflow |

Most rows land on Task workflows, as the design predicted: they are each
steps for a particular kind of work. `hands-on-keyboard` and its contract
doc are the one Mode pair in the inventory. `global/CLAUDE.md` (a
`global-guidance` row, not `skill`/`command`/`contract`) is the Invariants
example already used in the categories table above; it is not repeated in
this table because it falls outside the `skill`/`command`/`contract` types
this table draws from.

`provider-interop.md` does not appear in this table at all — it is ledgered
in `capabilities.json`'s `not_a_capability` list, not a `contract` row — and
it would be a poor fit for the Provider adapters category even if it were:
it *documents* what a provider adapter is and catalogs the ones that exist,
it isn't itself one. Force-fitting it into the table would misrepresent both
the doc and the category.

## Provider-specific differences stay outside

[provider-interop.md](provider-interop.md) treats non-equivalences between
Claude and Codex as permanent, not a migration phase to smooth over. This
contract's five categories and its precedence rule apply identically
regardless of which provider is executing: an invariant is an invariant, a
mode is a mode, whether the worker is a Claude Code session or a Codex
session following the same doc manually. Only the Provider adapters category
itself is provider-specific by definition — it exists precisely to hold the
differences the other four categories deliberately don't carry. This is what
satisfies #31's acceptance criterion 5, "provider-specific differences
remain outside the portable composition contract where appropriate."

## Where this fits

- [delegation-profiles.md](delegation-profiles.md) supplies the authority
  ladder this doc's inheritance section extends to the full category stack.
- [delegated-implementation-packets.md](delegated-implementation-packets.md)
  supplies the "state outranks narration" rule this doc extends to
  contradictions, and is itself a task workflow classified above.
- [provider-interop.md](provider-interop.md) is the standing contract for
  what "provider adapter" means; this doc classifies existing adapters, it
  doesn't redefine them.
- [product-boundary.md](product-boundary.md) non-goal 1 (no workflow engine)
  is why this stays a classification-and-precedence doc, not automation.
