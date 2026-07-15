#!/usr/bin/env bash
#
# session-end-land.sh — leave the repo on clean, synced main, but only when
# lossless. Read-only inspection plus a fast-forward-only landing; never
# strands work. Run as the final step of /session-end.
#
# SAFE requires: a clean working tree (no tracked changes), the current branch
# already merged into origin/main (or already on main), and a local main that
# has not diverged from origin/main. When SAFE it switches to main and runs
# `git merge --ff-only origin/main`, then reports any fully-merged local
# branches as safe-to-delete (it never deletes them). Otherwise it mutates
# nothing and prints the blocking reason.
#
# Usage: bin/session-end-land.sh [--check] [--no-fetch]
#   --check     inspect and print the verdict only; never mutate.
#   --no-fetch  skip the best-effort `git fetch origin` (caller already fetched).
#
# Output: first stdout line is a machine-readable verdict token —
#   SAFE                     landed (or, with --check, would land)
#   BLOCKED: dirty-tree      uncommitted/staged tracked changes
#   BLOCKED: branch-unmerged current branch has commits not in origin/main
#   BLOCKED: main-diverged   local main has commits not in origin/main
#   BLOCKED: detached-head   HEAD is detached; no branch to reason about
#   ERROR: <reason>          not a git repo, no origin, or no origin/main
# followed by human-readable detail and any proposed commands.
#
# Exit codes:
#   0   SAFE (landed, or would-land under --check)
#   10  BLOCKED (a normal, expected outcome — not an error)
#   1   ERROR (environment problem)
#   64  usage error
#
set -uo pipefail

CHECK=0
FETCH=1
while [ $# -gt 0 ]; do
  case "$1" in
    -h | --help)
      awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
      exit 0
      ;;
    --check) CHECK=1 ;;
    --no-fetch) FETCH=0 ;;
    *)
      echo "session-end-land.sh: unknown argument '$1'" >&2
      exit 64
      ;;
  esac
  shift
done

MAIN="main"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: not a git repository"
  exit 1
fi
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: no 'origin' remote"
  exit 1
fi

if [ "$FETCH" -eq 1 ]; then
  git fetch origin --quiet 2>/dev/null ||
    echo "warning: git fetch origin failed; comparing against stale origin/$MAIN" >&2
fi

if ! git rev-parse --verify --quiet "origin/$MAIN" >/dev/null; then
  echo "ERROR: origin/$MAIN not found"
  exit 1
fi

cur="$(git branch --show-current)"
if [ -z "$cur" ]; then
  echo "BLOCKED: detached-head"
  echo "  HEAD is detached — check out a branch before ending the session."
  exit 10
fi

# dirty = any staged/unstaged change to a TRACKED file (untracked ?? ignored)
dirty="$(git status --porcelain --untracked-files=no)"
if [ -n "$dirty" ]; then
  echo "BLOCKED: dirty-tree"
  echo "  Uncommitted changes to tracked files — commit or stash first:"
  # shellcheck disable=SC2001 # multi-line var; ${//} can't do this substitution
  sed 's/^/    /' <<<"$dirty"
  exit 10
fi

# local main diverged from origin/main? (only if a local main exists)
if git rev-parse --verify --quiet "$MAIN" >/dev/null; then
  ahead_main="$(git rev-list --count "origin/$MAIN..$MAIN")"
  if [ "$ahead_main" -gt 0 ]; then
    echo "BLOCKED: main-diverged"
    echo "  Local $MAIN has $ahead_main commit(s) not on origin/$MAIN — resolve before landing."
    exit 10
  fi
fi

# current branch merged into origin/main? (trivially true when already on main)
if [ "$cur" != "$MAIN" ]; then
  if ! git merge-base --is-ancestor HEAD "origin/$MAIN"; then
    ahead="$(git rev-list --count "origin/$MAIN..HEAD")"
    echo "BLOCKED: branch-unmerged"
    echo "  Branch '$cur' has $ahead commit(s) not in origin/$MAIN."
    echo "  Merge its PR (or push and open one) before landing on $MAIN."
    exit 10
  fi
fi

# --- SAFE ---
if [ "$CHECK" -eq 1 ]; then
  echo "SAFE"
  if [ "$cur" != "$MAIN" ]; then
    echo "  Would switch $cur -> $MAIN and fast-forward to origin/$MAIN."
  else
    echo "  Would fast-forward $MAIN to origin/$MAIN (or already up to date)."
  fi
  exit 0
fi

if [ "$cur" != "$MAIN" ]; then
  if ! git switch "$MAIN" --quiet 2>/dev/null; then
    echo "ERROR: could not switch to $MAIN (is it checked out in another worktree?)"
    exit 1
  fi
fi
if ! git merge --ff-only "origin/$MAIN" --quiet 2>/dev/null; then
  echo "ERROR: could not fast-forward $MAIN to origin/$MAIN"
  exit 1
fi

echo "SAFE"
echo "  On $MAIN, up to date with origin/$MAIN."
deletable="$(git branch --merged "origin/$MAIN" --format '%(refname:short)' | grep -vx "$MAIN" || true)"
if [ -n "$deletable" ]; then
  echo "  Merged local branch(es) safe to delete (not deleted):"
  while IFS= read -r b; do
    [ -n "$b" ] && echo "    git branch -d $b"
  done <<<"$deletable"
fi
exit 0
