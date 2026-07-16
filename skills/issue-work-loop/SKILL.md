---
name: issue-work-loop
description: Use when picking up a repository issue and taking it from discovery to an honest end state — orienting to repo policy, deduplicating before claiming it, bounding and executing the fix, verifying real gates, and closing out with honest status. Automates the six-phase issue-work-loop contract for Claude by delegating each phase to Bindle-native skills; never lets implementation authority imply close/merge/publish authority.
---

# Issue work loop

## Overview

Thin Claude-native orchestrator for the six-phase issue work loop. The
normative source is the contract `docs/workflows/issue-work-loop.md` — this
skill only automates that contract for Claude, phase by phase, naming which
existing Bindle-native skill or doc governs each one. It does not restate
the contract's full reasoning and must never contradict it: if this skill
and the contract disagree, the contract wins.

## When to Use

- Picking up a repository issue (e.g. via `gh issue view`) with real intent
  to work it in this repo's checkout, from "orient" through "close out."
- Any point where a prior claim that an issue is "already done" or "in
  progress elsewhere" needs checking against real git/remote state rather
  than trusted narration.
- Deciding what a delegated worker may and may not do before Phase 4 starts.

When NOT to use:
- Multi-issue scheduling, wave computation, or deciding *which* issue to
  work next — out of scope for this loop (see the contract's non-goals) and
  the territory of a different fleet's tooling, not this skill.
- As authority to merge, close, or publish on your own say-so — see the
  two-authority invariant below; this skill never grants that by itself.

## The two-authority invariant (hard rule)

Repository mutation (editing, committing, branching, working in the
checkout) and external mutation (pushing, opening or merging a PR,
commenting/labeling/closing an issue, publishing, deploying) are separate
grants, never implied by each other. General permission to *implement* a
fix does not imply permission to *close, merge, publish, or deploy* it —
each external mutation needs its own explicit grant naming that exact
action. Opening a clean PR does not authorize merging it.

## The honesty rule (hard rule)

Never trust another agent's or a prior session's `done` claim without
checking it against the real checkout and the real remote — that is a
claim, not evidence. A tool or network failure produces `uncertain`, never
a false `already-done` or a false `not-started`. This is enforced
structurally in Phase 3 below, and holds at every other phase too.

## The six phases

1. **Orient — delegate to `domi-consumer`.** Read this repo's `CLAUDE.md`
   and resolve precedence per `docs/workflow-composition.md` where more than
   one workflow could apply. Inspect actual repo state — current branch,
   remotes, `git status` — never assume a branch or a clean tree. Identify
   the repo's real verification commands (Phase 5) and mutation boundaries
   (branch-and-PR? a hook blocking direct-to-main?). Run the `domi-consumer`
   skill to detect DomI drift and inherited policy categories, even when
   the issue looks unrelated to DomI.

2. **Discover & qualify.** Read the issue and its comments in full
   (`gh issue view <n> --comments`). Confirm it is actually open, actionable,
   and not blocked (no unresolved `blocked-by`, no explicit "don't start
   yet") — open-on-GitHub is a necessary check here, never sufficient; see
   Phase 3. Classify the delegation profile (Mechanical, Review, Research,
   Implementation, or Privileged) per `docs/delegation-profiles.md` — this
   bounds what a delegated worker may do in Phase 4, decided before Phase 4
   starts. Name the expected deliverable up front (analysis, local patch,
   branch, PR, issue update, or handoff) so Phase 6 can report against it
   honestly.

3. **Deduplicate before claiming — delegate to `bin/issue-dedup-scan.sh
   <issue-number>`.** No issue is claimed or reimplemented solely because
   its GitHub state is open. Run the helper before any repository mutation
   begins. It emits JSON on stdout, but **the verdict is carried in the
   exit code** — read the exit code first, not just the JSON body:

   | Exit | Verdict | What to do |
   |---|---|---|
   | `0` | `no-evidence` | Every sub-query ran and found nothing. Map to `not-started`; proceed to Phase 4. |
   | `3` | `evidence-found` | At least one sub-query surfaced a reference. The helper never self-classifies further — read the emitted `evidence` array yourself and classify by hand into `in-progress-elsewhere`, `already-done` (verified against real state, never narration), or `partially-done`. |
   | `4` | `uncertain` | At least one sub-query **failed** (tool/network error), not merely empty. **Stop, or explicitly degrade and report the gap. Never read this as "no prior work" — a failed query proved nothing.** |
   | `64` | usage error | Bad invocation (missing/non-numeric issue number); fix the call, not a verdict about the issue. |

   Exit `4` is structurally distinct from exit `0`: a query that errored is
   not the same as a query that ran clean and came back empty. Do not paper
   over a `4` by re-running until it happens to pass, and do not treat a
   partial or incomplete scan as a clean `0`.

4. **Bound & execute — delegate to `scoped-sequential-prs` /
   `fork-pr-flow`.** State the exact scope for this pass and its explicit
   non-goals before writing any code — this is what makes Phase 6's "did we
   do what we said" check possible. Select the minimal applicable workflow
   set, resolving overlap per `docs/workflow-composition.md` rather than
   stacking every workflow that could plausibly apply. If any part of the
   work is delegated, delegate only within the Phase 2 delegation profile's
   authority and never wider — see `docs/delegation-profiles.md` and, for a
   formally bounded unit of delegated work, `docs/delegated-implementation-packets.md`.
   Keep repository mutation and external mutation separate at every step.
   Preserve no-push/no-publish defaults unless explicitly overridden for
   this task; when work does reach a push or a PR, follow
   `scoped-sequential-prs` (single-purpose, ordered PRs rather than one
   large blob) and `fork-pr-flow` (where changes land, and never merging a
   PR you just opened without explicit authorization).

   Before the first repository mutation of an authorized pass, isolate the
   work: run `<bindle>/bin/objective-worktree.sh <branch>` — it fetches `origin`,
   resolves `origin/main` (or a `--base` ref) to a SHA, and creates the
   objective branch plus a dedicated worktree at that exact SHA. Do all
   mutation inside that worktree, leaving the primary checkout untouched.
   Read the emitted `READY: <path> <branch> <base-ref> <base-sha>` line and
   record those four provenance fields for close-out; on a `BLOCKED:` or
   `ERROR:` token, stop and report — never improvise the base or claim it was
   fresh. A read-only or plan-only pass (Phase-2 deliverable `analysis`, or
   a Review/Research profile) creates no worktree.

5. **Verify — delegate to `verify-then-commit`.** Run the repository's
   actual verification commands discovered in Phase 1 — tests, typecheck,
   lint, in whatever form the repo actually defines them — never assumed
   ones. Review the final diff and git state directly; a diff that "looks
   right" is not verified, running the gate is. Verify any claim that
   depends on remote state (a PR exists, a check passed, a branch is up to
   date) against the real remote, never a cached assumption or another
   agent's narration. Report exactly one of **not run** (say why), **failed**
   (say what failed), or **passed** per check — never "should be fine" or
   "looks correct" in place of an actual run.

6. **Close out honestly — delegate to `session-continuity`.** If the
   deliverable is a PR, open it (or update the existing one) only if
   PR-opening authority was granted per the two-authority invariant. Comment
   on or update the issue with real evidence — what was found, what was
   done, what remains — never a comment implying completion the
   verification didn't establish. Close the issue only when the closure
   criteria are actually met AND closure authority was explicitly granted;
   meeting the criteria without the authority is not sufficient, and vice
   versa. If the work is incomplete, leave a durable session note or
   handoff via the `session-continuity` skill (`/session-end` / `/handoff`)
   rather than letting context evaporate. If adjacent work was noticed along
   the way, record it explicitly rather than silently folding it into this
   pass's scope.

   After verification, stop at the deliverable-disposition decision: present
   one `AskUserQuestion` whose options are only the actions valid for this
   deliverable and state — derived from the Phase-2 deliverable, the real
   verification state, existing PR/issue state, and the explicit authority
   granted — marking a recommended action only when it is safe under the
   authority actually granted: when only implementation authority was
   granted, the recommended default is the option that performs no external
   mutation (leave the deliverable as-is), and every externally-mutating
   option (push, PR creation/update, issue comment, close, merge, release)
   stays offered but unmarked; mark one of those recommended only when its
   specific grant is already in hand (selecting it in the decision is itself
   what supplies the grant, so it need not be pre-marked to be chosen). Ask a
   follow-up only when the chosen action genuinely needs one (draft vs. ready
   PR; close with or without a comment). No answer = leave the deliverable
   as-is, perform no external mutation, and report disposition undecided.
   Prefer an explanatory comment on issue closure; allow no-comment closure
   only on an explicit choice or
   when there is genuinely no useful explanation to preserve.

## Boundaries / red flags

- Do not skip Phase 3 because the issue "looks straightforward" — the dedup
  scan is the only structural defense against reimplementing already-shipped
  work.
- Do not treat a Phase 3 exit `4` (`uncertain`) as license to proceed as if
  it were `not-started`.
- Do not let "I implemented it" slide into "so I'll merge/close/publish it"
  without checking the two-authority invariant for that specific external
  action.
- Do not substitute a DomI-fleet tool (`check-done`, `list-issues`,
  `dispatch-issue`, `gh-issues`, `verify-plan`) for any phase — this skill
  and the contract it automates are deliberately fleet-independent; those
  are a different fleet's tooling, not Bindle's.
- Do not skip the Phase-4 worktree isolation for a mutating pass, and do not
  claim the base was `origin/main` without the helper's emitted base SHA — a
  narrated base is not a verified one.

**REQUIRED BACKGROUND:** `docs/workflows/issue-work-loop.md` (the full
six-phase contract, the two-authority invariant, and the state vocabulary
this skill automates but does not restate).
