---
name: fork-pr-flow
description: Use when opening, targeting, or describing a pull request and deciding where changes land — whether the repo is a fork (origin vs upstream, avoiding "upstream into upstream") or one you own where changes should reach your own main via PR rather than a direct commit; also when unsure whether to push at all.
---

# fork-pr-flow

## Overview

When you work on a **fork**, `origin` is your copy and `upstream` is the source you contribute back to. A PR must go **from your fork's branch → upstream's base branch**. The two most common failures are (1) opening a PR whose head and base are *both* upstream (nothing to merge, or the wrong direction), and (2) pushing to a remote the operator wanted to push themselves.

**Default to the least surprising action: commit locally and stop. Never push to `origin`, `upstream`, or a deploy target unless explicitly asked.**

## When to Use

- The repo has both an `origin` and an `upstream` remote (`git remote -v` shows two different owners).
- You're about to open a PR and need to pick head/base.
- A PR preview shows "upstream:main ← upstream:main" or otherwise merges upstream into itself.
- The operator says "make a PR to the upstream", "PR from my fork", or "how do I contribute this back".

When NOT to use:
- Single-remote repo you own directly (just push a branch and PR normally).
- The operator explicitly named the remote/branch to push — follow that.

## The mental model

```
your fork (origin)          the source (upstream)
  owner: you                  owner: maintainer
  feature/x  ──────PR────────▶  main   ← PR lands here
```

A cross-fork PR: **head** = `your-username:feature/x`, **base** = `upstream-owner:main`.

## Keep main as a clean mirror; branch off it

`main` is never worked on directly — it only ever tracks `upstream/main`. Every unit of work is a `feature/<x>` or `fix/<x>` branch cut fresh off an up-to-date `main`, one PR-able unit per branch. This keeps PRs conflict-free and reviewable against current upstream.

```bash
git fetch upstream
git switch main && git merge --ff-only upstream/main   # main = upstream, no local commits to fast-forward past
git switch -c feature/x                                 # always branch off fresh main
# ...work, commit on the branch...
git fetch upstream && git rebase upstream/main          # before the PR: make it apply cleanly
```

Enforce it mechanically with the `no-commit-to-branch` pre-commit hook (`args: [--branch, main]`) so a direct commit to `main` is rejected rather than merely discouraged. If the hook blocks you, that's the control working — branch, don't `--no-verify`.

## When you own the repo (you ARE the upstream)

No fork — one `origin` you control. The branch discipline is identical; only the PR target changes. `main` is still never committed to directly.

- `main` tracks `origin/main` and is the published source of truth. You advance it by **merging PRs on GitHub**, then `git switch main && git pull`.
- Branch `feature/<x>` off fresh `main`; commit there; `git push origin feature/<x>` (this push is expected — it's your own repo — but still don't push to deploy targets without asking).
- Open the PR on your own repo: `gh pr create --base main --head feature/<x>`. Here head and base are both `origin`, which is correct — this is *not* the "upstream into upstream" mistake, which only applies to forks.
- Squash-merge, delete the branch, `git switch main && git pull`.

The only difference from the fork case: the PR base is **your** `origin/main`, not `upstream/main`. The `no-commit-to-branch` hook applies the same either way.

## Quick Reference

| Step | Command |
|------|---------|
| Confirm remotes | `git remote -v` |
| Ensure your branch is on origin | `git push origin feature/x` (only if asked / for a PR) |
| Open cross-fork PR | `gh pr create --repo <upstream-owner>/<repo> --base main --head <your-user>:feature/x` |
| Draft PR (edit body on GitHub later) | add `--draft` |
| Verify it landed on the right base | `gh pr view --repo <upstream-owner>/<repo> --json baseRefName,headRefName,headRepositoryOwner` |

`gh pr create` run from a fork clone often defaults `--repo` to **upstream** and `--head` to your branch automatically. Always print and confirm the base/head before creating.

## PR description

Write a body that leads with **why this matters and what value it delivers**, not a file-by-file changelog. Structure:

1. **What & why** — the problem this solves, in one or two sentences.
2. **Value** — what the maintainer/users get from merging it.
3. **Changes** — brief bullets, grouped, not per-line.
4. **Testing** — what you ran to verify.

Draft-first is fine: `--draft` and refine the body in the GitHub UI.

## Common Mistakes

- **PR base is upstream's default via the fork's own branch of the same name** → GitHub shows "upstream:main ← upstream:main". Fix `--head` to `<your-user>:branch`.
- **Pushing to `upstream`** — you usually lack rights, and it's never wanted. Push to `origin` only, and only when a PR is actually requested.
- **Auto-pushing to deploy targets** (HuggingFace, Vercel, PyPI) as a side effect — the operator handles these. Stop and ask.
- **File-by-file PR body** — leads with mechanics instead of value. Lead with why.
