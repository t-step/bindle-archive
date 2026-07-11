#!/usr/bin/env bash
#
# test-notes-home.sh — exercise bin/notes-home.sh end to end against
# throwaway directories. Every case runs with HOME pointed at a temp dir and
# an explicit --home Claude home, so nothing touches your real ~/.claude,
# ~/.bindle, ~/.claude/settings.json, or any environment variable.
#
# Usage: bin/test-notes-home.sh
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NH="$REPO_ROOT/bin/notes-home.sh"

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

contains() { grep -qF -- "$1" <<<"$2"; }       # contains NEEDLE HAYSTACK
not_contains() { ! grep -qF -- "$1" <<<"$2"; } # not_contains NEEDLE HAYSTACK
exit_is() { [ "$1" -eq "$2" ]; }               # exit_is ACTUAL EXPECTED

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# run_nh HOME_DIR CLAUDE_HOME [env VAR=... ...] -- ARGS...
# Runs notes-home.sh with a scrubbed environment: fake $HOME, no
# BINDLE_NOTES_DIR / CLAUDE_KIT_NOTES_DIR unless the caller passes them.
run_nh() {
  local home_dir="$1" claude_home="$2"
  shift 2
  local envs=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    envs+=("$1")
    shift
  done
  shift # the --
  env -u BINDLE_NOTES_DIR -u CLAUDE_KIT_NOTES_DIR HOME="$home_dir" \
    ${envs[@]+"${envs[@]}"} "$NH" --home "$claude_home" "$@"
}

# snapshot DIR — path + kind + checksum fingerprint (see test-doctor.sh).
snapshot() {
  local d="$1" p
  [ -e "$d" ] || {
    echo "MISSING $d"
    return 0
  }
  find "$d" | sort | while IFS= read -r p; do
    if [ -L "$p" ]; then
      printf 'L %s -> %s\n' "$p" "$(readlink "$p")"
    elif [ -f "$p" ]; then
      printf 'F %s %s\n' "$p" "$(shasum -a 256 "$p" | awk '{print $1}')"
    elif [ -d "$p" ]; then
      printf 'D %s\n' "$p"
    fi
  done
}

# ===========================================================================
echo "1. status — resolution chain:"
H="$TMP/h1"
CH="$TMP/h1/.claude"
mkdir -p "$CH"

out="$(run_nh "$H" "$CH" -- status 2>&1)"
check "default resolves to \$HOME/.bindle" contains "$H/.bindle" "$out"
check "default source is named" contains "default" "$out"

out="$(run_nh "$H" "$CH" BINDLE_NOTES_DIR="$TMP/vault" -- status 2>&1)"
check "BINDLE_NOTES_DIR wins" contains "$TMP/vault" "$out"
check "env source is named" contains "BINDLE_NOTES_DIR" "$out"

out="$(run_nh "$H" "$CH" CLAUDE_KIT_NOTES_DIR="$TMP/old" -- status 2>&1)"
check "deprecated alias resolves" contains "$TMP/old" "$out"
check "deprecated alias is flagged" contains "deprecated" "$out"

# project note counts
mkdir -p "$H/.bindle/projects/alpha/sessions" "$H/.bindle/projects/beta"
touch "$H/.bindle/projects/alpha/sessions/2026-01-01-x.md"
out="$(run_nh "$H" "$CH" -- status 2>&1)"
check "lists project alpha" contains "alpha" "$out"
check "lists project beta" contains "beta" "$out"

# status also reports whether the env key is persisted in settings.json
printf '{"env":{"BINDLE_NOTES_DIR":"%s"}}\n' "$TMP/vault" >"$CH/settings.json"
out="$(run_nh "$H" "$CH" -- status 2>&1)"
check "reports persisted settings key" contains "settings.json" "$out"

echo
echo "2. status is read-only:"
before="$(snapshot "$H")"
run_nh "$H" "$CH" -- status >/dev/null 2>&1
after="$(snapshot "$H")"
check "home byte-identical before/after status" [ "$before" = "$after" ]

echo
echo "3. set — preview by default (no TTY, no --apply):"
H="$TMP/h3"
CH="$TMP/h3/.claude"
mkdir -p "$CH"
printf '{"model":"opus","env":{"OTHER":"keep"}}\n' >"$CH/settings.json"
before="$(snapshot "$CH")"
out="$(run_nh "$H" "$CH" -- set "$TMP/h3-vault" 2>&1)"
status=$?
check "preview exits 0" exit_is "$status" 0
check "preview shows the key" contains "BINDLE_NOTES_DIR" "$out"
check "preview shows the target path" contains "$TMP/h3-vault" "$out"
check "preview says nothing was written" contains "no changes written" "$out"
check "preview mentions --apply" contains -- "--apply" "$out"
after="$(snapshot "$CH")"
check "settings.json untouched by preview" [ "$before" = "$after" ]

echo
echo "4. set --apply — surgical write:"
out="$(run_nh "$H" "$CH" -- set "$TMP/h3-vault" --apply 2>&1)"
status=$?
check "apply exits 0" exit_is "$status" 0
check "apply announces the backup" contains "backup" "$out"
check "notes dir was created" [ -d "$TMP/h3-vault" ]
check "takes-effect-next-session notice" contains "next session" "$out"

py() { python3 -c "$1" "$CH/settings.json"; }
val="$(py 'import json,sys; print(json.load(open(sys.argv[1]))["env"]["BINDLE_NOTES_DIR"])')"
check "env key written" [ "$val" = "$TMP/h3-vault" ]
val="$(py 'import json,sys; print(json.load(open(sys.argv[1]))["env"]["OTHER"])')"
check "sibling env key preserved" [ "$val" = "keep" ]
val="$(py 'import json,sys; print(json.load(open(sys.argv[1]))["model"])')"
check "unrelated top-level key preserved" [ "$val" = "opus" ]
backup_count="$(find "$CH" -name 'settings.json.bak-*' | wc -l | tr -d ' ')"
check "exactly one backup created" [ "$backup_count" = "1" ]
backup_file="$(find "$CH" -name 'settings.json.bak-*' | head -1)"
val="$(python3 -c 'import json,sys; print("BINDLE_NOTES_DIR" not in json.load(open(sys.argv[1])).get("env",{}))' "$backup_file")"
check "backup holds the pre-write content" [ "$val" = "True" ]

echo
echo "5. set --apply with no settings.json:"
H="$TMP/h5"
CH="$TMP/h5/.claude"
mkdir -p "$CH"
out="$(run_nh "$H" "$CH" -- set "$TMP/h5-vault" --apply 2>&1)"
status=$?
check "apply exits 0" exit_is "$status" 0
val="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["env"]["BINDLE_NOTES_DIR"])' "$CH/settings.json")"
check "minimal settings.json created with the key" [ "$val" = "$TMP/h5-vault" ]

echo
echo "6. set refuses invalid settings JSON:"
H="$TMP/h6"
CH="$TMP/h6/.claude"
mkdir -p "$CH"
printf '{not json\n' >"$CH/settings.json"
before="$(snapshot "$CH")"
out="$(run_nh "$H" "$CH" -- set "$TMP/h6-vault" --apply 2>&1)"
status=$?
check "invalid JSON exits 1" exit_is "$status" 1
check "invalid JSON is reported" contains "not valid JSON" "$out"
after="$(snapshot "$CH")"
check "invalid settings.json left untouched" [ "$before" = "$after" ]

echo
echo "7. set warns when the target is inside a git repo:"
H="$TMP/h7"
CH="$TMP/h7/.claude"
mkdir -p "$CH" "$TMP/h7-repo"
git -C "$TMP/h7-repo" init -q
out="$(run_nh "$H" "$CH" -- set "$TMP/h7-repo/notes" 2>&1)"
check "git-repo warning printed" contains "git repo" "$out"
out="$(run_nh "$H" "$CH" -- set "$TMP/h7-vault" 2>&1)"
check "no git-repo warning outside one" not_contains "git repo" "$out"

echo
echo "8. reset:"
H="$TMP/h8"
CH="$TMP/h8/.claude"
mkdir -p "$CH"
printf '{"env":{"BINDLE_NOTES_DIR":"/x","OTHER":"keep"},"model":"opus"}\n' >"$CH/settings.json"
before="$(snapshot "$CH")"
out="$(run_nh "$H" "$CH" -- reset 2>&1)"
check "reset preview leaves file untouched" [ "$before" = "$(snapshot "$CH")" ]
check "reset preview says nothing written" contains "no changes written" "$out"
out="$(run_nh "$H" "$CH" -- reset --apply 2>&1)"
status=$?
check "reset --apply exits 0" exit_is "$status" 0
val="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("BINDLE_NOTES_DIR" not in d.get("env",{}), d["env"]["OTHER"], d["model"])' "$CH/settings.json")"
check "key removed, siblings preserved" [ "$val" = "True keep opus" ]
out="$(run_nh "$H" "$CH" -- reset --apply 2>&1)"
status=$?
check "reset when unset is a no-op exit 0" exit_is "$status" 0
check "no-op is stated" contains "not set" "$out"

echo
echo "9. migrate — copy, never delete:"
H="$TMP/h9"
CH="$TMP/h9/.claude"
mkdir -p "$CH"
mkdir -p "$H/.bindle/projects/alpha/sessions" "$H/.bindle/projects/beta"
printf 'alpha note\n' >"$H/.bindle/projects/alpha/sessions/2026-01-01-x.md"
printf 'deny\n' >"$H/.bindle/private-denylist.txt"
DEST="$TMP/h9-vault"
mkdir -p "$DEST/projects/beta"
printf 'already here\n' >"$DEST/projects/beta/profile.md"

out="$(run_nh "$H" "$CH" -- migrate "$DEST" 2>&1)"
check "migrate preview says nothing written" contains "no changes written" "$out"
check "migrate preview names alpha" contains "alpha" "$out"

out="$(run_nh "$H" "$CH" -- migrate "$DEST" --apply 2>&1)"
status=$?
check "migrate --apply exits 0" exit_is "$status" 0
check "alpha copied" [ -f "$DEST/projects/alpha/sessions/2026-01-01-x.md" ]
check "denylist copied" [ -f "$DEST/private-denylist.txt" ]
check "existing beta skipped" [ "$(cat "$DEST/projects/beta/profile.md")" = "already here" ]
check "skip is reported" contains "beta" "$out"
check "source alpha still present" [ -f "$H/.bindle/projects/alpha/sessions/2026-01-01-x.md" ]
check "source is never deleted notice" contains "old" "$out"

echo
echo "10. usage errors:"
out="$(run_nh "$TMP/h10" "$TMP/h10/.claude" -- bogus 2>&1)"
status=$?
check "unknown subcommand exits 2" exit_is "$status" 2
out="$(run_nh "$TMP/h10" "$TMP/h10/.claude" -- set 2>&1)"
status=$?
check "set without a path exits 2" exit_is "$status" 2

# ===========================================================================
echo
echo "tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
