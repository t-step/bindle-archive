# Design: `/session-end` lands the repo on clean, synced `main`

Date: 2026-07-15
Status: approved (brainstorm complete, pending plan)

## Problem

`/session-end` today is entirely read-only toward the working repo: it writes a
session note to the notes home, proposes `gh` label changes, and reconciles the
profile-proposals queue — but never touches the working tree. A session
therefore ends wherever it happened to be: often on a feature branch whose PR
has already merged (a stale local branch), or on a `main` that is behind
`origin/main`. The operator then hand-runs `git switch main && git pull` at the
start of the next session.

The goal: `/session-end` should, as its **final** step, leave the repo on
`main` fast-forwarded to `origin/main` — but only when doing so is **lossless**.
It must never strand or hide real work (uncommitted changes, an unmerged
branch, a diverged `main`).

## Decisions (from brainstorming)

1. **Attempt-if-safe, else report.** Auto switch-to-main + `--ff-only` pull only
   when safe. When unsafe, mutate nothing; report the exact blocker so the
   operator resolves it. Never a blind force.
2. **Report merged branches, don't delete.** On a safe landing, name any
   fully-merged local branch as safe-to-delete with the exact `git branch -d`
   command — but never run it. Mirrors how session-end already proposes (but
   never runs) `gh` label mutations.
3. **Safety logic lives in a tested helper**, not in command prose. A small
   `bin/session-end-land.sh` makes the git determination and performs the safe
   landing; `bin/test-session-end-land.sh` covers it deterministically in
   fixture repos. Rationale: the failure mode (misjudging "safe" and stranding
   work) is safety-critical, and a script is deterministically unit-testable
   where LLM prose is not.

## Component: `bin/session-end-land.sh`

Read-only inspection plus safe landing. One optional flag:

- `--check` — inspect and print the verdict only; **never mutates**. Used by
  the test suite and available as a dry-run preview.

### Inspection inputs

- Dirty tree: any uncommitted or staged changes to tracked files
  (`git status --porcelain` filtered to tracked). Untracked files alone do not
  block a switch and are not a blocker.
- Current branch's merge status vs `origin/main`
  (`git merge-base --is-ancestor HEAD origin/main`).
- Local `main` vs `origin/main`: behind (fast-forwardable), up-to-date, ahead,
  or diverged.
- Best-effort `git fetch origin` first (network read; updates remote-tracking
  refs). If offline, warn and proceed against the existing `origin/main` ref
  rather than hard-failing.

### Verdicts

- **SAFE** — clean tree AND (already on `main` OR current branch is an ancestor
  of `origin/main`) AND local `main` is not diverged from `origin/main`.
  Action: `git switch main` (if not already there), then
  `git merge --ff-only origin/main`. Print the resulting landed state, and name
  any local branch fully merged into `origin/main` as safe-to-delete with its
  exact `git branch -d <branch>` command (report only). Exit `0`.
- **BLOCKED** — mutates nothing; prints the reason plus proposed remediation
  commands. Distinct exit code (e.g. `10`) so the command can branch on it.
  Reasons:
  - `dirty-tree` — lists the offending tracked files.
  - `branch-unmerged` — current branch has commits not in `origin/main`; report
    the ahead-count and hint to open/merge its PR.
  - `main-diverged` — local `main` has commits not in `origin/main`; report and
    refuse (never force).
- **ERROR** — not a git repo, no `origin` remote, etc. Exit `1`.

Output is structured (a leading `SAFE` / `BLOCKED:<reason>` / `ERROR:<reason>`
token on stdout) so `commands/session-end.md` can render it faithfully into the
reply and the session note's **decisions** section.

### Known fail-safe limitation

A **squash**-merged branch is not an ancestor of `origin/main`, so it reads as
`branch-unmerged` and is reported BLOCKED rather than auto-landed. This is
conservative by design — it never strands work; it only declines to auto-land a
case it cannot prove lossless. This repo merges PRs with merge commits, so the
common path lands cleanly.

## Component: `bin/test-session-end-land.sh`

Deterministic tests in throwaway fixture git repos (each with a local
`origin` remote so `origin/main` comparisons work offline). Cases:

- SAFE from a merged feature branch → asserts HEAD ends on `main`, up to date,
  and the merged branch is reported safe-to-delete (and still exists — not
  deleted).
- SAFE from a `main` that is behind `origin/main` → asserts fast-forward
  happened.
- Already on clean, up-to-date `main` → no-op SAFE.
- BLOCKED `dirty-tree` → asserts no mutation, correct file list.
- BLOCKED `branch-unmerged` → asserts no mutation, ahead-count reported.
- BLOCKED `main-diverged` → asserts no mutation.
- `--check` on a SAFE case → asserts verdict printed but HEAD unchanged.

## Edits to existing files

- **`commands/session-end.md`** — add a final step (after the note is written
  and the privacy pass) that runs `bin/session-end-land.sh`, renders its verdict
  into the reply, and folds the outcome into the note's **decisions**. Extend
  the `allowed-tools` frontmatter to permit `bin/session-end-land.sh`,
  `git switch`, `git fetch`, and `git merge --ff-only`.
- **`skills/session-continuity/SKILL.md`** — reword Rule 1's read-only clause to
  carve out the landing: session-end may, as its final step, switch to and
  fast-forward `main` (a lossless navigation), but still never creates,
  modifies, or deletes tracked files, and never makes commits, in the repo. The
  anti-leak intent (no notes/artifacts written into the repo) is unchanged.
- **`capabilities.json`** — two `not_a_capability` ledger rows for the new bin
  scripts (helper + its test), matching the existing `bin/*.sh` ledger shape.
- **`CHANGELOG.md`** — an Unreleased "Changed"/"Added" entry.

## Ordering

Landing is the **last** action of `/session-end` — after the session note is
written and the privacy pass runs — so the note captures the feature-branch
context (branch name, commits, `git log`) before HEAD moves to `main`.

## Verification

- `bin/test-session-end-land.sh` is the RED→GREEN gate for the git logic
  (deterministic; stronger than subagent reps for this kind of decision code).
- Confirm the new `bin/test-*.sh` is picked up by `make test` / `make check`
  per the repo's existing `bin/test-*.sh` convention.
- `make check` green before every commit; land the work on this
  `feature/session-end-land-on-main` branch and PR to `main` per repo
  discipline.

## Out of scope

- Deleting branches automatically (report only).
- Any push, tag, or remote-mutating action.
- Handling squash-merge auto-landing (reported BLOCKED; acceptable fail-safe).
- Changing the note-writing, label-reconciliation, or profile-proposal steps.
