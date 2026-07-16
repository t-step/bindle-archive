#!/usr/bin/env bash
#
# objective-worktree.sh — create an isolated worktree for authorized
# repository-mutating objective work, based on a freshly-fetched origin/main
# (or a caller-specified base). Emits the resolved base SHA so a caller cannot
# merely claim the base was fresh. Phase-4 adapter for the issue-work-loop
# contract (docs/workflows/issue-work-loop.md).
#
# Usage: bin/objective-worktree.sh <branch> [--base <ref>] [--check] [--no-fetch]
#   <branch>     objective branch to create (caller decides feature/ vs fix/).
#   --base <ref> base ref to resolve (default: origin/main).
#   --check      inspect + print verdict only; create nothing.
#   --no-fetch   skip git fetch (caller already fetched).
#
# Output: first stdout line is a machine-readable verdict token —
#   READY: <worktree-path> <branch> <base-ref> <base-sha>  created / would-create
#   BLOCKED: origin-unavailable   fetch or origin resolution failed
#   BLOCKED: base-unavailable     base ref does not resolve
#   BLOCKED: branch-exists        branch already exists
#   BLOCKED: worktree-occupied    worktree path already exists
#   ERROR: <reason>               not a git repo, no origin
# The verdict token is the only stdout line; any human-readable detail is
# written to stderr.
#
# Exit codes: 0 READY · 10 BLOCKED · 1 ERROR · 64 usage error
#
set -uo pipefail

BRANCH=""
BASE="origin/main"
CHECK=0
FETCH=1

while [ $# -gt 0 ]; do
  case "$1" in
    -h | --help)
      awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
      exit 0
      ;;
    --base)
      BASE="${2:-}"
      [ -n "$BASE" ] || {
        echo "objective-worktree.sh: --base needs a ref" >&2
        exit 64
      }
      shift 2
      ;;
    --check)
      CHECK=1
      shift
      ;;
    --no-fetch)
      FETCH=0
      shift
      ;;
    -*)
      echo "objective-worktree.sh: unknown flag '$1'" >&2
      exit 64
      ;;
    *)
      [ -z "$BRANCH" ] || {
        echo "objective-worktree.sh: unexpected argument '$1'" >&2
        exit 64
      }
      BRANCH="$1"
      shift
      ;;
  esac
done

[ -n "$BRANCH" ] || {
  echo "objective-worktree.sh: missing <branch>" >&2
  exit 64
}

verdict() {
  echo "$1"
  [ -n "${2:-}" ] && echo "$2" >&2
  return 0
}

# resolve the primary checkout root via the shared (common) git dir, so
# worktrees always land under the primary repo's .worktrees/ even when this
# helper is invoked from inside a linked worktree.
COMMON_DIR="$(git rev-parse --git-common-dir 2>/dev/null)" || {
  verdict "ERROR: not a git repository" ""
  exit 1
}
COMMON_DIR="$(cd "$COMMON_DIR" && pwd)" # make absolute regardless of git version
ROOT="$(dirname "$COMMON_DIR")"

git -C "$ROOT" remote get-url origin >/dev/null 2>&1 || {
  verdict "ERROR: no origin remote" ""
  exit 1
}

if [ "$FETCH" -eq 1 ]; then
  if ! git -C "$ROOT" fetch --quiet origin 2>/dev/null; then
    verdict "BLOCKED: origin-unavailable" "git fetch origin failed"
    exit 10
  fi
fi

BASE_SHA="$(git -C "$ROOT" rev-parse --verify --quiet "$BASE^{commit}" 2>/dev/null)" || true
if [ -z "$BASE_SHA" ]; then
  verdict "BLOCKED: base-unavailable" "cannot resolve base ref '$BASE'"
  exit 10
fi

if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  verdict "BLOCKED: branch-exists" "branch '$BRANCH' already exists"
  exit 10
fi

LEAF="${BRANCH##*/}"
WT="$ROOT/.worktrees/$LEAF"
if [ -e "$WT" ]; then
  verdict "BLOCKED: worktree-occupied" "path '$WT' already exists"
  exit 10
fi

if [ "$CHECK" -eq 1 ]; then
  verdict "READY: $WT $BRANCH $BASE $BASE_SHA" "would create worktree at base $BASE_SHA (--check)"
  exit 0
fi

if ! git -C "$ROOT" worktree add --quiet "$WT" -b "$BRANCH" "$BASE_SHA" 2>/dev/null; then
  verdict "ERROR: worktree add failed" "git worktree add '$WT' -b '$BRANCH' '$BASE_SHA' failed"
  exit 1
fi

verdict "READY: $WT $BRANCH $BASE $BASE_SHA" "created worktree at base $BASE_SHA"
exit 0
