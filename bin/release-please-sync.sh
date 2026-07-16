#!/usr/bin/env bash
#
# release-please-sync.sh — syncs VERSION + RELEASE-MANIFEST.json onto the
# open Release Please release-PR branch (issue #137).
#
# release-please-config.json used to list VERSION under extra-files, but
# Release Please's generic file updater only rewrites lines carrying an
# x-release-please-version annotation comment — Bindle's bare VERSION has
# none, so that entry was a silent no-op (removed; see release-please-config.json).
# This script closes the gap: it reads the version Release Please already
# computed (from the release PR branch's .release-please-manifest.json) and
# writes it into VERSION, then regenerates RELEASE-MANIFEST.json
# (bin/release-manifest.py) — both in one follow-up commit pushed onto the
# SAME PR branch. It never creates a new PR, never touches main, never tags,
# merges, or publishes.
#
# Run from inside the target repo's working tree — same convention as
# bin/release-strategy.sh and bin/release-strategies/local-release-please.sh
# (no chdir to a fixed location; operates on the caller's cwd via `git -C`).
#
# Usage:
#   bin/release-please-sync.sh dry-run
#   bin/release-please-sync.sh apply --approval-token <ephemeral>
#
set -euo pipefail

die() {
  echo "release-please-sync: $1" >&2
  exit "${2:-1}"
}

verb="${1:-}"
shift || true

case "$verb" in
  dry-run) ;;
  apply)
    token=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --approval-token)
          token="${2:-}"
          shift 2
          ;;
        --approval-token=*)
          token="${1#*=}"
          shift
          ;;
        *) shift ;;
      esac
    done
    [ -n "$token" ] || die "apply refused — no approval token" 3
    ;;
  *)
    die "unknown verb '${verb:-<none>}' (want: dry-run|apply)" 2
    ;;
esac

command -v gh >/dev/null 2>&1 || die "gh CLI not found on PATH" 4

repo_root="$(git rev-parse --show-toplevel)"

# --- find the release PR ----------------------------------------------------
prs_json="$(gh pr list --state open --label "autorelease: pending" \
  --json number,headRefName,baseRefName)"
pr_count="$(printf '%s' "$prs_json" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
[ "$pr_count" -ne 0 ] || die "no open PR labeled 'autorelease: pending' — nothing to sync" 10
[ "$pr_count" -eq 1 ] || die "found $pr_count PRs labeled 'autorelease: pending' — expected exactly 1, refusing to guess" 11

pr_field() { printf '%s' "$prs_json" | python3 -c "import json,sys; print(json.load(sys.stdin)[0][\"$1\"])"; }
pr_number="$(pr_field number)"
head_ref="$(pr_field headRefName)"
base_ref="$(pr_field baseRefName)"

git -C "$repo_root" fetch -q origin "$head_ref" "$base_ref"

manifest_version() { # manifest_version <ref>
  git -C "$repo_root" show "$1:.release-please-manifest.json" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["."])'
}

new_version="$(manifest_version "origin/$head_ref")"
old_version="$(manifest_version "origin/$base_ref")"
branch_version="$(git -C "$repo_root" show "origin/$head_ref:VERSION")"

if [ "$branch_version" = "$new_version" ]; then
  echo "release-please-sync: VERSION already in sync at $new_version (PR #$pr_number, $head_ref)"
  exit 0
fi

echo "release-please-sync: PR #$pr_number ($head_ref) — VERSION $branch_version -> $new_version"

if [ "$verb" = "dry-run" ]; then
  echo "release-please-sync: dry-run — would sync VERSION and regenerate RELEASE-MANIFEST.json on $head_ref"
  exit 0
fi

# --- apply: sync onto the PR branch in an isolated worktree -----------------
wt_dir="$repo_root/.worktrees/release-please-sync"
wt_branch="_release-please-sync"

git -C "$repo_root" worktree remove --force "$wt_dir" >/dev/null 2>&1 || true
git -C "$repo_root" worktree prune >/dev/null 2>&1 || true
rm -rf "$wt_dir"

cleanup() {
  git -C "$repo_root" worktree remove --force "$wt_dir" >/dev/null 2>&1 || true
  git -C "$repo_root" branch -D "$wt_branch" >/dev/null 2>&1 || true
}
trap cleanup EXIT

git -C "$repo_root" worktree add -q -B "$wt_branch" "$wt_dir" "origin/$head_ref"

(
  cd "$wt_dir"
  printf '%s\n' "$new_version" >VERSION
  bin/check.sh
  bin/test-install.sh
  python3 bin/release-manifest.py --version "$new_version" --previous "$old_version" --verify-determinism
  python3 bin/release-manifest.py --version "$new_version" --previous "$old_version" --emit
  git add VERSION RELEASE-MANIFEST.json
  git commit -q -m "chore: sync VERSION + RELEASE-MANIFEST.json to v${new_version}"
  git push -q origin "HEAD:$head_ref"
)

echo "release-please-sync: pushed VERSION + RELEASE-MANIFEST.json sync onto $head_ref (PR #$pr_number)"
