#!/usr/bin/env bash
#
# test-session-context.sh — exercise bin/session-context.sh against throwaway
# git repos and a scrubbed environment. Never touches the real ~/.bindle,
# ~/.claude, or any real git repo.
#
# Usage: bin/test-session-context.sh
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so the fixture-repo git
# calls below would hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SC="$REPO_ROOT/bin/session-context.sh"

pass=0 fail=0
check() { # check "description" command...
  local desc="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  ✗ %s\n' "$desc"
    fail=$((fail + 1))
  fi
}

contains() { grep -qF -- "$1" <<<"$2"; }
not_contains() { ! grep -qF -- "$1" <<<"$2"; }
exit_is() { [ "$1" -eq "$2" ]; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# run_sc HOME_DIR [env VAR=... ...] -- ARGS...
run_sc() {
  local home_dir="$1"
  shift
  local envs=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    envs+=("$1")
    shift
  done
  shift # the --
  env -u BINDLE_NOTES_DIR -u CLAUDE_KIT_NOTES_DIR HOME="$home_dir" \
    ${envs[@]+"${envs[@]}"} "$SC" "$@"
}

echo "1. non-git directory:"
PLAIN="$TMP/plain"
mkdir -p "$PLAIN"
H1="$TMP/h1"
out="$(run_sc "$H1" -- --cwd "$PLAIN" 2>&1)"
status=$?
check "exits 0 outside a git repo" exit_is "$status" 0
check "reports not a git repo" contains "not a git repo" "$out"
check "notes home defaults to \$HOME/.bindle" contains "$H1/.bindle" "$out"
check "no session note yet" contains "(none yet)" "$out"
check "no handoff yet" contains "(none yet)" "$out"

echo
echo "2. clean git repo, no notes yet:"
REPO="$TMP/myrepo"
mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" checkout -q -b main
git -C "$REPO" config user.email test@example.com
git -C "$REPO" config user.name test
touch "$REPO/f.txt"
git -C "$REPO" add f.txt
git -C "$REPO" commit -q -m init
H2="$TMP/h2"
out="$(run_sc "$H2" -- --cwd "$REPO" 2>&1)"
check "reports project name" contains "project: myrepo" "$out"
check "reports branch and clean" contains "branch main, clean" "$out"

echo
echo "3. dirty git repo:"
echo "change" >>"$REPO/f.txt"
echo "new" >"$REPO/new.txt"
out="$(run_sc "$H2" -- --cwd "$REPO" 2>&1)"
check "reports 1 modified" contains "1 modified" "$out"
check "reports 1 untracked" contains "1 untracked" "$out"
git -C "$REPO" checkout -q -- f.txt
rm -f "$REPO/new.txt"

echo
echo "4. BINDLE_NOTES_DIR override and latest-note selection:"
VAULT="$TMP/vault"
mkdir -p "$VAULT/projects/myrepo/sessions" "$VAULT/projects/myrepo/handoffs"
touch "$VAULT/projects/myrepo/sessions/2026-01-01-first.md"
touch "$VAULT/projects/myrepo/sessions/2026-06-01-second.md"
touch "$VAULT/projects/myrepo/handoffs/2026-03-01-only.md"
out="$(run_sc "$H2" BINDLE_NOTES_DIR="$VAULT" -- --cwd "$REPO" 2>&1)"
check "notes home reflects override" contains "$VAULT" "$out"
check "override source is named" contains "BINDLE_NOTES_DIR" "$out"
check "picks the newest session note" contains "2026-06-01-second.md" "$out"
check "does not surface the older note" not_contains "2026-01-01-first.md" "$out"
check "picks the only handoff" contains "2026-03-01-only.md" "$out"

echo
echo "5. deprecated CLAUDE_KIT_NOTES_DIR alias:"
OLD="$TMP/old-vault"
mkdir -p "$OLD"
out="$(run_sc "$H2" CLAUDE_KIT_NOTES_DIR="$OLD" -- --cwd "$REPO" 2>&1)"
check "resolves via deprecated alias" contains "$OLD" "$out"
check "flags it as deprecated" contains "deprecated" "$out"

echo
echo "6. persisted BINDLE_NOTES_DIR in settings.json (no env var set):"
H6="$TMP/h6"
CH6="$H6/.claude"
mkdir -p "$CH6"
PERSISTED="$TMP/persisted-vault"
printf '{"env":{"BINDLE_NOTES_DIR":"%s"}}\n' "$PERSISTED" >"$CH6/settings.json"
out="$(run_sc "$H6" -- --cwd "$REPO" --home "$CH6" 2>&1)"
check "resolves persisted settings.json value" contains "$PERSISTED" "$out"
check "names settings.json as the source" contains "settings.json" "$out"

echo
echo "7. gh unavailable degrades silently:"
H7="$TMP/h7"
out="$(env -u BINDLE_NOTES_DIR -u CLAUDE_KIT_NOTES_DIR HOME="$H7" PATH="/usr/bin:/bin" "$SC" --cwd "$REPO" 2>&1)"
status=$?
check "still exits 0 without gh" exit_is "$status" 0
check "issues line reports unavailable" contains "issues: (unavailable)" "$out"

echo
echo "8. is read-only (never writes anywhere):"
before="$(find "$VAULT" | sort)"
run_sc "$H2" BINDLE_NOTES_DIR="$VAULT" -- --cwd "$REPO" >/dev/null 2>&1
after="$(find "$VAULT" | sort)"
check "notes vault untouched" [ "$before" = "$after" ]

echo
echo "9. unknown flag is a usage error:"
out="$(run_sc "$H2" -- --bogus 2>&1)"
status=$?
check "unknown flag exits 2" exit_is "$status" 2

echo
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
