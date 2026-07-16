# Delegated implementation packets

The reusable contract for turning an approved issue into a bounded,
subagent-ready implementation packet — so the same guardrails don't have to be
retyped into every delegation prompt.

A **packet** is the executable specification of *one* PR-able unit of work: the
exact files to read, the single observable outcome, what must not change, how to
verify it, and precisely which mutations are authorized. It is a document a
maintainer writes (or an issue already carries) and hands to a delegated worker
— a Sonnet subagent, a Codex session, or a future self picking up cold.

This is **not** a workflow engine, an agent runtime, or an execution loop
([product-boundary.md](product-boundary.md) non-goal 1). It is the definition of
a good packet. It deliberately references, rather than restates, the neighboring
contracts:

- **Which workflows apply and how they compose** is
  [workflow-composition.md](workflow-composition.md)'s composition and
  precedence contract, issue #31. A packet *selects* the minimal applicable
  set; it does not define precedence.
- **What a delegated worker of a given risk level may do** is
  [delegation-profiles.md](delegation-profiles.md)'s ladder (Mechanical,
  Review, Research, Implementation, Privileged), issue #32. A packet *names*
  a profile; it does not define the ladder.
- **The full discover → deduplicate → execute → verify → close-out loop** is
  issue #60's issue work loop. A packet is the artifact consumed at #60's
  "Bound and execute" step; it does not replace the loop around it.
- **What executes, when, and where its output may go** is the
  [runtime security & privacy contract](runtime-security-privacy.md). A packet's
  authority section speaks that contract's language: repository mutation is
  class C2, external-system mutation (push, PR, `gh` writes, publish) is C5, and
  the two are never granted together implicitly.

## Two governing rules

Every packet is subject to two rules that a worker may not relax:

1. **Repository and remote state outrank agent narration.** A convincing report
   is not evidence. "Done", "tests pass", and "the PR is open" are claims to be
   verified against the actual checkout, the actual command output, and the
   actual remote — never trusted because a prior agent asserted them. A worker
   must not accept another worker's `done` without re-checking state.
2. **A packet grants no mutation authority it does not explicitly state.**
   Authority is allow-listed, never inferred. Permission to edit files is not
   permission to commit; permission to commit is not permission to push, open a
   PR, comment on an issue, or close it; permission to open a PR is never
   permission to merge. Anything the packet does not name is out of scope.

## The ten sections

A complete packet has these sections. Omitting one is a defect, not brevity —
if a section is genuinely empty (e.g. no manual checks), say so explicitly
rather than dropping it.

1. **Read first** — the exact authoritative files and issues the worker must
   read before acting, in priority order (project instructions, the governing
   contracts, the issue and its comments). Precedence is part of the packet, not
   left to the worker to guess.
2. **Preflight** — the checks that must hold before work starts: current branch
   and that it is not `main`; working-tree status is clean; the PR base is
   correct; and, for an authorized repository-mutating packet, that the work
   runs in a dedicated worktree whose branch is based on a freshly-resolved
   `origin/main` (or the mandated base) SHA, not a stale local `main`; the
   issue is open, actionable, and not blocked; named dependencies are
   satisfied. A failed preflight is a stop condition, not something to fix
   silently.
3. **Bounded objective** — one PR-able outcome stated in observable terms ("the
   audit's two matrix rows read *provider-specific* and a decision section
   exists"), not a direction of travel ("improve portability"). One packet, one
   objective.
4. **Expected artifacts** — the files or artifact classes expected to change,
   named as tightly as the work allows. This is the positive scope; section 5 is
   its negative.
5. **Do not change** — named files, surfaces, behaviors, and adjacent concerns
   that must stay untouched even though the worker will notice them. Explicit
   exclusions are how a capable model is stopped from widening scope.
6. **Verification** — the exact commands to run (e.g. `make check`) and their
   expected result, plus any manual or real-provider checks that a command
   cannot cover. Report `not run`, `failed`, and `passed` as distinct states;
   never round a skipped check up to green.
7. **External mutation authority** — a per-action allow-list. State separately
   whether the worker may: edit files, commit, push, open/update a PR, comment
   on or label the issue, and close it. Absent an explicit grant, each is
   denied. Repository mutation (C2) and external-system mutation (C5) are named
   independently; a general "implement this" never implies push, PR, merge, or
   publish. The repository's no-push / no-self-merge defaults hold unless this
   section overrides them in writing.
8. **Stop conditions** — the situations in which the worker must stop and report
   instead of proceeding: ambiguity it cannot resolve from the packet, a failed
   preflight or prerequisite, authority that conflicts with a governing
   contract, scope that has grown beyond the bounded objective, or behavior it
   cannot verify. Stopping and reporting is a success, not a failure.
9. **Noticed, not done** — a place to record adjacent problems and opportunities
   observed while working, *without* acting on them. This is how scope stays
   bounded without losing the observation: it becomes a follow-up issue, not a
   silent edit in this PR.
10. **Closeout evidence** — what the worker returns: the final diff or repository
    state, the workspace provenance (the worktree path, branch, base ref, and
    base SHA the work ran in), the exact commands run and their real results,
    any remaining uncertainty, and the concrete PR/issue state (numbers, URLs,
    open/closed). Closeout is evidence, not narration — it is checkable
    against rule 1.

## Plan-only pass vs. authorized implementation pass

Run a packet in one of two modes, and say which in the authority section:

- **Plan-only (first pass).** The worker reads section 1, runs the section-2
  preflight, and produces a plan: the concrete edits it *would* make, the files
  it would touch, and any ambiguities or stop conditions it hit — but makes **no
  repository or external mutation**. This is the safe default for an unfamiliar
  packet, a large blast radius, or a worker whose reliability on this shape of
  task is unproven. It maps to #32's Review/Research authority.
- **Authorized implementation (second pass).** The worker executes the plan
  within the stated authority: edits the expected artifacts, runs verification,
  and performs exactly the mutations section 7 allows. It maps to #32's
  Implementation authority, and to Privileged only if section 7 explicitly
  grants a C5 action.

Splitting the passes is cheap and catches scope and authority errors before any
state changes. A packet may require the plan pass to be reviewed before the
implementation pass is authorized.

## Reusable template

Copy this into an issue body or a handoff prompt and fill every section.

```markdown
## Packet: <one-line objective>

### Read first
- <file or issue, highest authority first>
- <…>

### Preflight
- On a `feature/<x>` or `fix/<x>` branch cut from `main`, not `main` itself.
- Working tree clean; PR base is `main` (or: <base>).
- For a mutating packet: work runs in a dedicated worktree; branch based on a
  fresh `origin/main` (or `<base>`) SHA `<sha>`, not stale local `main`.
- Issue #<n> is open, actionable, and unblocked; dependencies <…> satisfied.

### Bounded objective
<One PR-able outcome in observable terms.>

### Expected artifacts
- <file or artifact class expected to change>

### Do not change
- <named file / surface / behavior that must stay untouched>

### Verification
- `<exact command>` → <expected result>
- Manual / real-provider check: <what to observe, or "none">

### External mutation authority
- Edit files: <yes/no>   Commit: <yes/no>   Push: <yes/no>
- Open/update PR: <yes/no>   Comment/label issue: <yes/no>   Close issue: <yes/no>
- Mode: <plan-only | authorized implementation>
- Defaults: no push and no self-merge unless a line above overrides them.

### Stop conditions
- <ambiguity / failed prerequisite / conflicting authority / scope growth /
  unverifiable behavior — stop and report>

### Noticed, not done
- <record adjacent observations here; do not implement them in this packet>

### Closeout evidence
- Final diff/state, commands run + real results, remaining uncertainty,
  PR/issue numbers and their state.
- Workspace provenance: worktree `<path>`, branch `<branch>`, base ref `<ref>`,
  base SHA `<sha>`.
```

## Worked example

A packet reconstructed from issue #71 ("Isolate provider-specific invocation
wording in `session-continuity` and `hands-on-keyboard`"), a real bounded unit
that shipped under this discipline.

```markdown
## Packet: record the provider-wording decision for two skills (#71)

### Read first
- CLAUDE.md / AGENTS.md — the standing "Claude assets remain Claude-native"
  Phase 1 rule (highest authority; it constrains the answer).
- docs/product-boundary.md — asset-conversion non-goal.
- docs/skill-portability-audit.md — the matrix rows and options being decided.
- Issue #71 and its comments.

### Preflight
- On `docs/71-provider-wording-decision`, cut from `main`, not `main`.
- Working tree clean; PR base `main`.
- #71 is open and unblocked (evidence PR #70 already merged).

### Bounded objective
The audit records a decision (option 1 vs 2) per skill; both skill matrix rows
read a final disposition; U7 and cleanup items 1–2 are resolved. `make check`
green.

### Expected artifacts
- docs/skill-portability-audit.md
- CHANGELOG.md

### Do not change
- skills/session-continuity/SKILL.md and skills/hands-on-keyboard/SKILL.md —
  no wording edits (option 2 was chosen precisely to leave them Claude-native).
- Any installer, doctor, hook, or runtime behavior.

### Verification
- `make check` → all checks pass.
- Manual: confirm the diff is confined to the audit doc + CHANGELOG.

### External mutation authority
- Edit files: yes   Commit: yes   Push: yes
- Open/update PR: yes   Comment/label issue: no   Close issue: no (PR "Resolves
  #71" closes it on merge; merge is the owner's).
- Mode: authorized implementation.
- Defaults hold: no self-merge.

### Stop conditions
- If the compliant choice required amending the Phase 1 rule (option 1), stop —
  that is a product decision, not a cleanup edit.

### Noticed, not done
- The #57 courtesy comment naming resolved wave-2 candidates is a separate
  external-mutation action; record it, don't assume authority for it.

### Closeout evidence
- Diff: audit doc + CHANGELOG only. `make check`: passed. PR #72 open against
  `main`, "Resolves #71". Issue left open for the owner to merge/close.
```

The example shows the discipline the contract exists to enforce: the "Do not
change" section names the two `SKILL.md` files explicitly, so a worker cannot
drift into the tempting-but-forbidden neutralize-in-place edit; and the
authority section grants commit + PR but withholds issue-close and self-merge,
so the owner keeps the final gate.

## Where this fits

- [CONTRIBUTING.md](../CONTRIBUTING.md) covers branch/commit discipline and the
  pressure-test loop for *skills*; a packet is the delegation-side companion for
  *implementation* work.
- [docs/issue-tracking.md](issue-tracking.md) covers issue state and labels; a
  packet is what a `status: ready` issue should contain to be delegable.
- The packet does not grant, and cannot be read to grant, any authority the
  [runtime security & privacy contract](runtime-security-privacy.md) reserves
  for explicit per-action human approval.
