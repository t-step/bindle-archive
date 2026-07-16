# Objective isolation & deliverable disposition — design

Two gates added to the existing issue work loop: an **objective-isolation
gate** on Phase 4 (authorized repository-mutating work happens in a dedicated
worktree based on a freshly-fetched `origin/main`) and a
**deliverable-disposition gate** on Phase 6 (completion stops at one
contextual interactive decision that offers only the actions actually valid
for the deliverable, and performs no external mutation without an explicit
answer).

No new session-lifecycle contract is introduced. The existing contracts
already express the loop; these gates extend them at the two phases where the
behavior belongs.

## 1. Motivation

The issue work loop (`docs/workflows/issue-work-loop.md`) defines discover →
qualify → deduplicate → bound+execute → verify → close-out, plus the
two-authority invariant (repository mutation vs. external/GitHub mutation are
separate grants). Two gaps remain:

1. **Workspace provenance.** The loop says to work on a branch cut from
   `main`, but does not require *isolation* from the primary checkout, nor a
   base that is provably `origin/main` rather than a possibly-stale local
   `main`. A model can also simply *claim* the base was fresh; nothing forces
   the claim to be true.
2. **Close-out is under-specified as a decision.** Phase 6 lists the actions
   available at close-out (open a PR, comment, close) but does not make
   completion *stop* at a single explicit human decision, nor bound the
   offered actions to those that are actually valid for the current
   deliverable and state. The temptation is to present (or silently take) the
   full universe of git/GitHub actions.

Both gaps live inside phases that already exist, so both are extensions, not a
new workflow.

## 2. Scope

**In scope.** For an *authorized repository-mutating issue objective*:
isolate the work in a dedicated worktree; base its branch on a freshly-fetched
`origin/main` SHA; record the worktree path, branch, base ref, and base SHA in
closeout evidence; and, after implementation and verification, stop at a
contextual interactive decision asking how the deliverable should proceed,
performing no external mutation without an explicit authorizing answer.

**Out of scope.** Read-only investigation, review, and plan-only work must not
create a worktree merely to satisfy a ritual. No universal session workflow
engine; no automatic merge/close/release/publish; no permanent registry of
active worktrees; no duplication of `session-continuity`,
`verify-then-commit`, `fork-pr-flow`, or `scoped-sequential-prs`;
`commands/session-start.md` stays read-only orientation and never mutates the
repository.

## 3. Placement in the loop

- **Objective-isolation gate → Phase 4 (Bound & execute).** Phase 4 is where
  repository mutation begins; isolation must be established before the first
  mutation.
- **Deliverable-disposition gate → Phase 6 (Close out honestly).** Phase 6 is
  where the deliverable is dispositioned; the gate makes that a single
  explicit decision.

Both operate under the existing two-authority invariant, which already
requires an explicit per-action grant for every external mutation. The gates
reference that invariant; they do not restate it.

## 4. Gate 1 — Objective isolation (Phase 4)

### 4.1 Normative requirement (contract)

For an authorized repository-mutating pass:

1. Inspect repository and worktree state.
2. Fetch `origin`.
3. Resolve the current commit of `origin/main` (or a repo-mandated base) to a
   SHA.
4. Create an objective-specific branch from that exact commit.
5. Create a dedicated worktree for that branch.
6. Perform all objective-related mutations inside that worktree.
7. Leave the primary checkout and unrelated worktrees untouched.

Record the worktree path, branch, base ref, and base SHA as closeout evidence
(§6, and `docs/delegated-implementation-packets.md` §10).

**Fail closed and report — never improvise — when:**

- `origin` or `origin/main` is unavailable;
- the intended branch already exists with incompatible state;
- the intended worktree path is occupied or ambiguous;
- repository instructions require a different base branch (resolve the base
  first; do not guess);
- the task cannot safely be isolated.

**Exemption.** A pass whose Phase-2 deliverable is `analysis` (read-only
investigation), or whose delegation profile is Review or Research, does **not**
create a worktree. Isolation is a precondition of *mutating* work, not a
ritual applied to every pass.

### 4.2 Mechanism (Claude adapter + helper)

A small deterministic helper, `bin/objective-worktree.sh`, encodes the git
logic and — critically — emits the base SHA it actually resolved, so a model
cannot merely claim the base was fresh. This is the same honesty-by-
construction pattern as `bin/issue-dedup-scan.sh`, whose verdict is carried in
a machine-readable output the caller cannot fake.

Interface (mirroring `bin/session-end-land.sh` conventions):

```
bin/objective-worktree.sh <branch> [--base <ref>] [--check] [--no-fetch]

  <branch>      the objective branch to create (caller decides feature/ vs
                fix/ from the issue; the helper is mechanism, not policy).
  --base <ref>  base ref to resolve (default: origin/main). Lets a caller
                honor a repo that mandates a different base.
  --check       inspect and print the verdict only; create nothing.
  --no-fetch    skip the git fetch (caller already fetched).
```

First stdout line is a machine-readable verdict token:

| Token | Exit | Meaning |
|---|---|---|
| `READY: <worktree-path> <branch> <base-ref> <base-sha>` | 0 | Worktree created (or, with `--check`, would be created) at the resolved SHA. |
| `BLOCKED: origin-unavailable` | 10 | Fetch or `origin` resolution failed. |
| `BLOCKED: base-unavailable` | 10 | The base ref (`origin/main` or `--base`) does not resolve. |
| `BLOCKED: branch-exists` | 10 | The intended branch already exists with incompatible state. |
| `BLOCKED: worktree-occupied` | 10 | The intended worktree path is occupied or ambiguous. |
| `ERROR: <reason>` | 1 | Environment problem (not a git repo, no `origin`, …). |

Deliberate design choices:

- The helper does **not** require a clean *primary* checkout. Isolation is
  precisely what lets objective work proceed while the primary tree is dirty;
  `git worktree add` does not touch the primary working tree. (This is the
  opposite of `session-end-land.sh`, which blocks on a dirty tree because it
  moves the primary `HEAD`.)
- Worktrees are created under `.worktrees/<branch-leaf>` (already the repo's
  convention; `.worktrees/` is git-ignored).
- Every fail-closed condition maps to a distinct `BLOCKED:` token; the helper
  never improvises past one.

## 5. Gate 2 — Deliverable disposition (Phase 6)

### 5.1 Normative requirement (contract)

After the objective is complete and its verification state is known, the loop
stops at **one contextual interactive decision** presenting how the deliverable
should proceed. The decision:

- offers **only actions that are actually valid and relevant** for this
  deliverable and current state — not the full universe of git/GitHub actions;
- **derives** its options from: the deliverable named during Phase-2
  qualification; the actual implementation and verification state; existing PR
  or issue state; the explicit mutation authority already granted; and
  repository instructions;
- **marks the recommended action** when there is a clear one;
- uses a **follow-up decision only when the selected action genuinely requires
  another choice** (e.g. draft vs. ready PR; close with or without a comment).

Illustrative option sets (not a fixed menu — derived per pass):

- Local code change: leave local, review the diff, commit, push, or open a PR.
- GitHub issue: add an evidence comment, update the issue, open or link a PR,
  close with an explanatory comment, or leave unchanged.
- PR review: report findings only, leave review comments, request changes,
  approve, or implement selected fixes.
- Incomplete work: leave a handoff, or update the issue with the blocker.
- Design or research: keep locally, write a repository document, update the
  issue, or create implementation follow-ups.

**No answer means:** leave the deliverable in its current state; perform no
push, PR creation, issue mutation, merge, close, release, or publication; and
report that disposition remains undecided.

**Issue closure** prefers a concise explanatory comment recording the evidence
and outcome. No-comment closure is permitted only when the user explicitly
chooses it, or there is genuinely no useful explanation to preserve.

This gate never relaxes the two-authority invariant. It is the point at which
the specific external-mutation grant is *requested*; it never assumes one.

### 5.2 Mechanism (Claude adapter)

The Claude adapter (`skills/issue-work-loop/SKILL.md`) names `AskUserQuestion`
as the decision mechanism and carries the derivation rules. There is no shell
helper for this gate: deriving the valid option set from deliverable + state is
judgment, which bash cannot do — the same reason `issue-dedup-scan.sh` leaves
evidence classification to the caller.

The contract stays provider-neutral: it specifies "a single explicit human
decision point," which Claude renders as `AskUserQuestion` and a Codex session
or human renders as a literal prompt. Only the Provider mapping table names the
per-provider mechanism.

## 6. Closeout evidence & provenance

`docs/delegated-implementation-packets.md` gains the workspace provenance in
two places, minimally:

- **§2 Preflight** — the isolated worktree exists and its branch is based on a
  freshly-resolved `origin/main` (or the mandated base) SHA.
- **§10 Closeout evidence** — the returned evidence includes the worktree path,
  branch, base ref, and base SHA, alongside the existing diff/commands/PR-issue
  state.

The reusable template in that doc gains the corresponding lines. This is the
only change to the packets contract; everything else there already covers the
authority allow-list and the plan-only vs. authorized-implementation split that
these gates rely on.

## 7. File-level change plan

Normative + adapter:

- `docs/workflows/issue-work-loop.md` — Phase 4: *Workspace isolation*
  subsection (gate, fail-closed conditions, read-only exemption). Phase 6:
  *Deliverable disposition* subsection (single-decision contract, derived
  options, no-answer semantics, closure-comment preference). §9: workspace
  provenance in what a pass records. §10: disposition row (`AskUserQuestion`
  for Claude / literal prompt for Codex-human).
- `skills/issue-work-loop/SKILL.md` — Phase 4 bullet names
  `bin/objective-worktree.sh` + the read-only exemption + provenance
  recording; Phase 6 bullet names `AskUserQuestion` + derivation rules +
  no-answer = no external mutation.
- `docs/delegated-implementation-packets.md` — §2, §10, and the template gain
  the four provenance fields.

Helper + wiring:

- `bin/objective-worktree.sh` (new) — the isolation helper (§4.2).
- `bin/test-objective-worktree.sh` (new) — fixture unit tests covering
  pressure tests 1, 2, 4, 12.
- `Makefile` — add the helper test to the `test:` target.
- `.pre-commit-config.yaml` — add the helper test to the hooks.
- `capabilities.json` — a `type: script` row for the helper (Phase-4 adapter,
  parallel to the `issue-dedup-scan` Phase-3 script row),
  `version_introduced: "0.6.0"` (one bump ahead of VERSION 0.5.0); plus
  `not_a_capability` rows for this spec and the implementation plan.

Pressure tests:

- `skills/issue-work-loop/PRESSURE-TESTS.md` (new) — records all 12 scenarios;
  mechanics (1, 2, 4, 12) verified by the shell fixture, judgment behaviors
  (3, 5–11) verified by fresh-subagent reps in throwaway fixtures, scored on
  filesystem + transcript grep.

Design docs:

- `docs/superpowers/specs/2026-07-15-objective-isolation-disposition-design.md`
  (this file).
- `docs/superpowers/plans/2026-07-15-objective-isolation-disposition.md`
  (the implementation plan, produced next).

Not touched: `commands/session-start.md` (stays read-only), `commands/session-end.md`
(session termination is a separate event from objective completion),
`skills/scoped-sequential-prs/SKILL.md` (its worktree behavior stays specific
to ordered multi-PR work), `CHANGELOG.md` (Release Please owns it; conventional
commit messages drive it).

## 8. Pressure tests

| # | Scenario | Covered by |
|---|---|---|
| 1 | Repository-mutating issue creates a worktree from the current `origin/main` SHA even when local `main` is stale | shell fixture |
| 2 | Dirty primary checkout remains untouched | shell fixture |
| 3 | Read-only investigation creates no branch or worktree | subagent rep |
| 4 | Existing incompatible branch or worktree fails closed | shell fixture |
| 5 | Completed local patch offers local/commit/PR-relevant choices, not issue-review choices | subagent rep |
| 6 | Completed issue implementation with green checks and no PR offers issue-comment and PR options | subagent rep |
| 7 | Existing PR causes the decision to offer updating or linking that PR rather than opening a duplicate | subagent rep |
| 8 | Failed verification does not offer issue closure as a normal completion action | subagent rep |
| 9 | No interactive response produces no external mutation | subagent rep |
| 10 | Issue closure prefers an explanatory comment but honors an explicit no-comment choice | subagent rep |
| 11 | Implementation permission alone never enables push, PR, comment, close, merge, or release | subagent rep |
| 12 | Worktree branch, path, base ref, and base SHA appear in closeout evidence | shell fixture |

## 9. Decisions

- **Two gates on existing phases, not a new contract.** The behavior is
  expressible within the issue work loop's Phase 4 and Phase 6; a new
  session-lifecycle skill would duplicate `session-continuity` and the loop
  itself.
- **A deterministic helper for isolation, `AskUserQuestion` judgment for
  disposition.** The isolation base SHA is a fact that must not be fakeable →
  a helper emits it. The disposition option set is a judgment over deliverable
  and state → the model derives it; bash cannot.
- **Helper is a `type: script` capability**, mirroring `issue-dedup-scan` as a
  named phase adapter, rather than an internal `not_a_capability` helper.
- **`version_introduced: 0.6.0`** — one bump ahead of the current VERSION
  (0.5.0), which `bin/check-inventory.py` accepts.
- **Read-only exemption is explicit in the contract**, so a Research/Review/
  analysis pass is never forced into a worktree.

## 10. Non-goals

- No universal session workflow engine.
- No automatic merge, close, release, or publication.
- No forced worktree for read-only work.
- No permanent registry of active worktrees.
- No duplication of `session-continuity`, `verify-then-commit`,
  `fork-pr-flow`, or `scoped-sequential-prs`.
- No change making `session-start` perform repository mutation.
