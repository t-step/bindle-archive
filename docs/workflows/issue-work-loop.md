# Issue work loop

The provider-neutral contract for taking a repository issue from discovery to
an **honest end state** — followed sequentially by a human, by Codex reading
this doc directly, or automated by a Claude-native skill. Resolves issue
`#60` (parent `#55`; related `#31`, `#32`, `#38`).

## 1. Purpose & scope

Bindle already has strong point workflows for branch/PR targeting
(`fork-pr-flow`), sequential PR scope (`scoped-sequential-prs`),
verification (`verify-then-commit`), and session continuity
(`session-continuity`). None of them defines the *complete loop*: how an
issue gets picked up, checked for prior work, bounded, executed, verified,
and closed out — in that order, with the same vocabulary, regardless of
which provider or human is driving.

This contract fixes that loop as six phases (below) plus a shared state
vocabulary. It is deliberately provider-neutral: Section 10 shows the same
six phases mapped onto Claude-native assets and onto what Codex (or a human)
does with the same doc, no fleet-specific tooling required on either side.

**Portability goal.** A session using only this repo's own assets — `gh`,
this doc, `bin/issue-dedup-scan.sh`, and the neighboring contracts named in
each phase below — can follow the loop completely. It never depends on
DomI-fleet skills such as `check-done`, `list-issues`, `dispatch-issue`,
`gh-issues`, or `verify-plan`; those are a separate fleet's tooling, not part
of Bindle, and referencing them here would silently reintroduce the
dependency this contract exists to remove.

**Non-goals (slice 1).** This is not a scheduler, a work queue, a
parallel-dispatch wave computation, an auto-merge policy, or an auto-close
policy. It does not decide *which* issue to work next, does not run multiple
issues concurrently, and never merges or closes anything on its own
authority — see the two-authority invariant below. It is a single-issue,
single-pass loop; multi-issue orchestration is out of scope, consistent with
`docs/product-boundary.md`'s non-goal 1 (no workflow engine or execution
runtime).

## 2. The two authorities (invariant)

Two kinds of mutation are separate grants, never implied by each other:

- **Repository mutation** — editing files, committing, creating or
  switching branches, working inside the checkout.
- **External mutation** — anything that changes state outside the local
  checkout on a real remote: `gh` issue comment/label/close, `git push`,
  opening a PR, merging a PR, publishing, deploying.

General permission to *implement* a fix does **not** imply permission to
*close, merge, publish, or deploy* it. Each external mutation needs its own
explicit grant naming that exact action — the same rule
`docs/delegation-profiles.md` states for Privileged authority, restated here
because this loop is where the temptation to conflate the two actually
shows up (a session that just opened a clean PR is not thereby authorized to
merge it, however confident it is that the PR is correct).

**Never trust another agent's `done` without checking the checkout and the
real remote.** A prior session's or subagent's narration that an issue is
"already handled" is a claim, not evidence — Phase 3 and Phase 5 both exist
to verify it against actual git/remote state before acting on it.

**A tool or network failure produces `uncertain` or a degraded report, never
a false `already-done` or false `not-started`.** This is the same principle
`bin/issue-dedup-scan.sh` encodes structurally in Phase 3 (see below), and it
applies at every phase: if a check couldn't run, say so — don't launder the
absence of a result into an optimistic one.

## 3. Phase 1 — Orient

- Read the repo's authoritative instructions and their precedence: this
  repo's own `CLAUDE.md` (or `AGENTS.md` for Codex), which names branch
  discipline, verification gates, and any repo-specific rules. Where more
  than one workflow could apply, resolve precedence per
  `docs/workflow-composition.md` rather than guessing.
- Inspect the actual repository state: current branch, remotes, `git
  status` — don't assume a branch or a clean tree.
- Identify the repo's real verification commands (tests/typecheck/lint —
  see Phase 5) and the mutation boundaries in force (is this a
  branch-and-PR repo? is direct-to-main blocked by a hook?).
- Detect whether this repo consumes DomI and what that implies:
  Claude sessions use the `domi-consumer` skill (which runs
  `bin/domi-status.sh` and interprets its verdict); a Codex session runs
  `bin/domi-status.sh` directly and reads the same exit code. Do not skip
  this even when the target issue looks unrelated to DomI — drift status can
  gate write-work per the repo's own policy.

## 4. Phase 2 — Discover & qualify

- Read the issue and its comments in full — `gh issue view <n> --comments`
  is the portable command; it works identically for a human, Claude, or
  Codex.
- Confirm the issue is actually open, actionable, and not blocked (no
  unresolved `blocked-by`, no explicit "don't start this yet"). An issue's
  GitHub state alone is a necessary check here, never a sufficient one — see
  Phase 3.
- Classify the task and the delegation profile it requires — Mechanical,
  Review, Research, Implementation, or Privileged, per
  `docs/delegation-profiles.md`. This determines what a delegated worker may
  and may not do in Phase 4, before any work starts.
- Name the expected deliverable up front: analysis, a local patch, a
  branch, a PR, an issue update/comment, or a handoff. Stating this before
  Phase 4 begins is what keeps Phase 6 honest — you can only report the
  deliverable you said you'd produce, or explain why it changed.

## 5. Phase 3 — Deduplicate before claiming

**No issue is claimed or reimplemented solely because its GitHub state is
open.** Before any repository mutation begins, run the bounded evidence
scan:

```
bin/issue-dedup-scan.sh <issue-number>
```

The helper emits JSON on stdout; **the verdict is carried in the exit
code**, not just the JSON body — read the exit code first:

| Exit | Verdict | What it means | What this phase does with it |
|---|---|---|---|
| `0` | `no-evidence` | Every sub-query (git log, in-repo specs, open PRs, merged PRs, issue comments) ran successfully and found nothing referencing the issue. | Map to state `not-started`. Proceed to Phase 4. |
| `3` | `evidence-found` | At least one sub-query surfaced a reference to the issue. | The helper does **not** self-classify further — read the emitted `evidence` array and classify by hand into `in-progress-elsewhere` (open PR/branch actively addressing it), `already-done` (merged PR/commit that resolves it, verified against real state), or `partially-done` (some but not all of the issue's scope is covered). |
| `4` | `uncertain` | At least one sub-query **failed** (tool/network error) — not merely empty. | STOP, or explicitly degrade and report the gap. Never read this as "no prior work" — a failed query proved nothing. |
| `64` | usage error | Bad invocation (missing/non-numeric issue number). | Fix the invocation; not a verdict about the issue. |

**The core invariant this phase enforces: a failed query is never proof of
no prior work.** Exit 4 (a sub-query that errored) is structurally distinct
from exit 0 (every sub-query ran and came back empty) — the helper is built
so the caller cannot accidentally collapse "I couldn't check" into "I
checked and it's clear." Do not paper over a `4` by re-running until it
happens to pass, and do not treat a partial/incomplete scan as a clean `0`.

## 6. Phase 4 — Bound & execute

- State the exact scope for this pass and its explicit non-goals, before
  writing any code — this is what makes Phase 6's "did we do what we said"
  check possible.
- Select the minimal applicable set of workflows for the task, resolving
  overlap per `docs/workflow-composition.md` rather than stacking every
  workflow that could plausibly apply.
- If any part of the work is delegated, delegate only within the authority
  named by the Phase 2 delegation profile and never wider — see
  `docs/delegation-profiles.md` and, for a formally bounded unit of
  delegated work, `docs/delegated-implementation-packets.md`.
- Keep repository mutation and external mutation separate at every step —
  editing/committing/branching is one grant; pushing, opening a PR, or
  touching the issue on GitHub is a different one (Section 2).
- Preserve the user's no-push/no-publish defaults unless explicitly
  overridden for this task. When the work does reach a push or a PR, follow
  `scoped-sequential-prs` (single-purpose, ordered PRs rather than one large
  blob) and `fork-pr-flow` (where changes land, and never merging a PR you
  just opened without explicit authorization).

### Workspace isolation (authorized repository-mutating passes)

Before the first repository mutation of an *authorized* pass, isolate the
work in a dedicated worktree:

1. Inspect repository and worktree state.
2. Fetch `origin`.
3. Resolve `origin/main` (or a repo-mandated base) to a commit SHA — the base
   is the freshly-fetched remote tip, never a possibly-stale local `main`.
4. Create the objective branch from that exact SHA.
5. Create a dedicated worktree for that branch; perform all objective-related
   mutations inside it, leaving the primary checkout and unrelated worktrees
   untouched.

Record the worktree path, branch, base ref, and base SHA as closeout evidence
(§9; `docs/delegated-implementation-packets.md` §10).

Fail closed and report — never improvise — when `origin` or `origin/main` is
unavailable, the intended branch already exists with incompatible state, the
worktree path is occupied or ambiguous, repository instructions require a
different base branch, or the task cannot safely be isolated.

**Read-only and plan-only passes are exempt.** A pass whose Phase-2
deliverable is `analysis`, or whose delegation profile is Review or Research
(`docs/delegation-profiles.md`), creates no branch or worktree — isolation is
a precondition of *mutating* work, not a ritual applied to every pass.

## 7. Phase 5 — Verify

- Run the repository's **actual** verification commands — discovered in
  Phase 1, not assumed. `verify-then-commit` is the governing skill: tests +
  typecheck + lint, in whatever form the repo actually defines them.
- Review the final diff and git state directly — a diff that "looks right"
  is not verified; running the gate is.
- If any claim depends on remote state (a PR exists, a check passed on
  GitHub, a branch is up to date), verify it against the **real** remote —
  never trust a cached assumption or another agent's narration of it
  (Section 2).
- Report exactly one of three states per check, with no optimistic
  rounding: **not run** (the check never executed — say why), **failed**
  (it ran and didn't pass — say what failed), or **passed** (it ran and
  came back green). Never report "should be fine" or "looks correct" in
  place of an actual run.

## 8. Phase 6 — Close out honestly

Depending on the Phase 5 result:

- If the deliverable is a PR, open it (or update the existing one) — only
  if PR-opening authority was granted per Section 2.
- Comment on or update the issue with real evidence: what was found, what
  was done, what remains — never a comment implying completion the
  verification didn't establish.
- **Close the issue only when the closure criteria are actually met AND
  closure authority was explicitly granted.** Meeting the criteria without
  the authority is not sufficient, and vice versa.
- If the work is incomplete, leave a durable session note or handoff rather
  than letting context evaporate — see `session-continuity` for the shape
  (project profile, session note, handoff) and where it lives (outside the
  project repo).
- If adjacent work was noticed along the way (a related bug, a stale
  reference, a follow-on issue), record it explicitly rather than silently
  folding it into this pass's scope — expanding scope without saying so
  defeats Phase 4's bounding.

### Deliverable disposition

Once Phase 5's verification state is known, stop at a single contextual
decision on how the deliverable should proceed. The decision offers only the
actions actually valid for this deliverable and state — not the full universe
of git/GitHub actions — derived from: the deliverable named in Phase 2, the
real implementation and verification state, existing PR/issue state, the
explicit mutation authority already granted (Section 2), and repository
instructions. Mark a recommended action only when it is safe under the
authority actually granted (Section 2): when only implementation authority was
granted, the recommended default is the option that performs no external
mutation — leave the deliverable in its current state — while every
externally-mutating option (push, PR creation/update, issue comment, close,
merge, release) stays offered but unmarked. Mark such an option recommended
only when its specific external grant is already in hand; selecting it in the
decision is itself what supplies the grant, so it need not be pre-marked to be
chosen. Ask a follow-up only when the chosen action genuinely needs one (draft
vs. ready PR; close with or without a comment).

**No answer means:** leave the deliverable in its current state; perform no
push, PR creation, issue mutation, merge, close, release, or publication; and
report that disposition remains undecided. This is the two-authority
invariant at its decision point — the specific external grant is *requested*
here, never assumed.

Prefer a concise explanatory comment when closing an issue; permit no-comment
closure only when the user explicitly chooses it, or there is genuinely no
useful explanation to preserve.

## 9. State vocabulary

**The five Phase 3 dedup verdicts** (mutually exclusive, one applies):

- `not-started` — no evidence of prior work found; safe to proceed to
  Phase 4.
- `in-progress-elsewhere` — evidence found; another PR/branch is actively
  addressing this issue.
- `already-done` — evidence found and verified; the issue is already
  resolved on real (not narrated) repository/remote state.
- `partially-done` — evidence found; some but not all of the issue's scope
  is covered by prior work.
- `uncertain` — a sub-query failed; the scan could not reach a verdict.
  Never treated as equivalent to `not-started`.

**The Phase 2/6 deliverable states** (what this pass actually produced, to
be named in Phase 2 and reported honestly in Phase 6):

- `analysis` — findings reported, no repository mutation.
- `local patch` — code changed in the working tree, not committed.
- `branch` — committed on a branch, not pushed.
- `PR` — pushed and a pull request opened (or updated).
- `issue update` — the issue itself commented on or relabeled with
  evidence.
- `handoff` — work incomplete; a durable note/handoff left per
  `session-continuity` for a future session to pick up.

**Workspace provenance** (recorded for every authorized repository-mutating
pass): the worktree path, branch, base ref, and base SHA the pass ran in —
carried into closeout evidence per `docs/delegated-implementation-packets.md`
§10. It is what makes "the base was `origin/main`" checkable rather than
narrated.

## 10. Provider mapping

Each phase's *requirement* is identical across providers; only the
mechanism differs. Claude automates the mechanical parts via a
Claude-native skill (Task 3 of this issue); Codex — or a human — follows
the same phase directly from this doc and the repo's shell scripts.

| Phase | Claude asset | Codex / human equivalent |
|---|---|---|
| 1. Orient | reads `CLAUDE.md`; `domi-consumer` skill (wraps `bin/domi-status.sh`) | reads `AGENTS.md`; runs `bin/domi-status.sh` directly |
| 2. Discover & qualify | `gh issue view` (portable); reads `docs/delegation-profiles.md` | identical — `gh issue view`; reads the same doc |
| 3. Deduplicate | runs `bin/issue-dedup-scan.sh <n>`, reads exit code + JSON | identical — same script, same exit-code contract |
| 4. Bound & execute | consults `docs/workflow-composition.md`, `docs/delegation-profiles.md`, `docs/delegated-implementation-packets.md`; applies `scoped-sequential-prs` / `fork-pr-flow` skills; isolates the pass via `bin/objective-worktree.sh` | reads the same contracts directly; applies the same rules manually (no skill runtime, same git/gh commands); creates the worktree with `git worktree add` from the fetched origin/main SHA |
| 5. Verify | `verify-then-commit` skill | runs the repo's actual test/typecheck/lint commands directly, applying the same all-green-or-fix rule |
| 6. Close out | `session-continuity` skill (via `/session-end` / `/handoff`) for notes; `gh`/`git` for PR and issue actions; the deliverable-disposition decision is one `AskUserQuestion` | writes the same note/handoff shape by hand per `session-continuity`'s documented conventions; identical `gh`/`git` actions; the disposition decision is a literal prompt to the human |

The contract in Sections 1–9 is what stays fixed. This table is the only
place providers are allowed to differ — consistent with
`docs/workflow-composition.md`'s Provider adapters category, which exists
precisely to hold such differences outside the portable phases themselves.
