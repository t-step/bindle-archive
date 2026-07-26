#!/usr/bin/env bash
#
# test-facts-index.sh — exercise bin/facts-index.sh against throwaway notes
# homes and a scrubbed environment. Never touches the real ~/.bindle,
# ~/.claude, or any real git repo.
#
# Usage: bin/test-facts-index.sh
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so the fixture-repo git
# calls below would hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FI="$REPO_ROOT/bin/facts-index.sh"

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
is_empty() { [ -z "$1" ]; }
line_count_is() { [ "$(grep -c . <<<"$2")" -eq "$1" ]; }
field_is() { # field_is N EXPECTED LINE
  [ "$(cut -f"$1" <<<"$3")" = "$2" ]
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# make_repo DIR — a throwaway git repo whose basename drives the project slug.
make_repo() {
  mkdir -p "$1"
  git -C "$1" init -q
  git -C "$1" config user.email t@example.com
  git -C "$1" config user.name t
  : >"$1/README.md"
  git -C "$1" add README.md
  git -C "$1" commit -qm init
}

# write_fact FILE SLUG TYPE DESCRIPTION — a well-formed fact per the
# session-continuity schema (type/modified nested under metadata).
write_fact() {
  cat >"$1" <<EOF
---
name: $2
description: "$4"
metadata:
  node_type: memory
  type: $3
  modified: 2026-07-26T00:00:00.000Z
---

Body of $2. This line must never appear in the index output.
EOF
}

# run_fi HOME_DIR [env VAR=... ...] -- ARGS...
run_fi() {
  local home_dir="$1"
  shift
  local envs=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    envs+=("$1")
    shift
  done
  shift # the --
  env -u BINDLE_NOTES_DIR -u CLAUDE_KIT_NOTES_DIR HOME="$home_dir" \
    ${envs[@]+"${envs[@]}"} "$FI" "$@"
}

REPO="$TMP/demo-proj"
make_repo "$REPO"
H="$TMP/home"
mkdir -p "$H"

echo "1. no notes home at all:"
out="$(run_fi "$H" -- --cwd "$REPO" 2>&1)"
status=$?
check "exits 0 with no notes home" exit_is "$status" 0
check "prints nothing" is_empty "$out"

echo
echo "2. notes home exists but the project has no facts/ dir:"
NOTES="$TMP/notes"
mkdir -p "$NOTES/projects/demo-proj/sessions"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
status=$?
check "exits 0 with no facts dir" exit_is "$status" 0
check "prints nothing" is_empty "$out"

echo
echo "3. empty facts/ dir:"
FACTS="$NOTES/projects/demo-proj/facts"
mkdir -p "$FACTS"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
status=$?
check "exits 0 on an empty facts dir" exit_is "$status" 0
check "prints nothing" is_empty "$out"

echo
echo "4. well-formed facts:"
write_fact "$FACTS/zeta-fact.md" zeta-fact project "the zeta thing is true"
write_fact "$FACTS/alpha-fact.md" alpha-fact feedback "always do the alpha thing"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "lists both facts" line_count_is 2 "$out"
check "emits slug TAB type TAB description" \
  contains "$(printf 'alpha-fact\tfeedback\talways do the alpha thing')" "$out"
check "sorts by slug (alpha before zeta)" \
  field_is 1 alpha-fact "$(head -1 <<<"$out")"
check "strips the quotes around description" not_contains '"always' "$out"
check "never reads a body" not_contains "must never appear" "$out"

echo
echo "5. MEMORY.md is the harness index, not a fact:"
# The real MEMORY.md is a list of markdown links; written link-free here so
# this fixture doesn't trip a link checker that scans the repo's own files.
cat >"$FACTS/MEMORY.md" <<'EOF'
- Alpha -> alpha-fact.md — hook
EOF
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "still lists only the two facts" line_count_is 2 "$out"
check "does not list MEMORY" not_contains "MEMORY" "$out"

echo
echo "6. malformed facts stay VISIBLE (an invisible fact is worse):"
cat >"$FACTS/no-frontmatter.md" <<'EOF'
Just a body, no frontmatter block at all.
EOF
cat >"$FACTS/unterminated.md" <<'EOF'
---
name: unterminated
description: "never closed"
EOF
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "lists all four files" line_count_is 4 "$out"
check "falls back to the filename slug" \
  contains "$(printf 'no-frontmatter\t\t')" "$out"
check "an unterminated block yields an empty description" \
  contains "$(printf 'unterminated\t\t')" "$out"
rm -f "$FACTS/no-frontmatter.md" "$FACTS/unterminated.md"

echo
echo "7. body lines can never leak into a field:"
cat >"$FACTS/decoy.md" <<'EOF'
---
name: decoy
description: "the real description"
metadata:
  type: reference
---

description: "a body line that looks like frontmatter"
name: not-the-slug
EOF
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "uses the frontmatter description" contains "the real description" "$out"
check "ignores the body decoy" not_contains "looks like frontmatter" "$out"
check "ignores the body name" not_contains "not-the-slug" "$out"
rm -f "$FACTS/decoy.md"

echo
echo "8. a tab inside a description cannot forge a column:"
printf -- '---\nname: tabby\ndescription: "a\tb"\nmetadata:\n  type: project\n---\n\nbody\n' \
  >"$FACTS/tabby.md"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "the tabby row still has exactly 3 fields" \
  [ "$(grep tabby <<<"$out" | awk -F'\t' '{print NF}')" = 3 ]
rm -f "$FACTS/tabby.md"

echo
echo "9. non-.md files and subdirectories are not facts:"
: >"$FACTS/notes.txt"
mkdir -p "$FACTS/subdir"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "still lists only the two facts" line_count_is 2 "$out"
rm -rf "$FACTS/notes.txt" "$FACTS/subdir"

echo
echo "10. resolution chain:"
KITNOTES="$TMP/kitnotes"
mkdir -p "$KITNOTES/projects/demo-proj/facts"
write_fact "$KITNOTES/projects/demo-proj/facts/kit-fact.md" \
  kit-fact project "from the deprecated var"
out="$(run_fi "$H" CLAUDE_KIT_NOTES_DIR="$KITNOTES" -- --cwd "$REPO" 2>&1)"
check "honors the deprecated CLAUDE_KIT_NOTES_DIR" contains "kit-fact" "$out"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" CLAUDE_KIT_NOTES_DIR="$KITNOTES" \
  -- --cwd "$REPO" 2>&1)"
check "BINDLE_NOTES_DIR outranks the deprecated var" not_contains "kit-fact" "$out"

HP="$TMP/persisted-home"
mkdir -p "$HP/.claude"
cat >"$HP/.claude/settings.json" <<EOF
{"env": {"BINDLE_NOTES_DIR": "$NOTES"}}
EOF
out="$(run_fi "$HP" -- --cwd "$REPO" --home "$HP/.claude" 2>&1)"
check "reads a persisted env.BINDLE_NOTES_DIR (the Codex path)" \
  contains "alpha-fact" "$out"

HB="$TMP/broken-home"
mkdir -p "$HB/.claude"
echo 'not json {' >"$HB/.claude/settings.json"
out="$(run_fi "$HB" -- --cwd "$REPO" --home "$HB/.claude" 2>&1)"
status=$?
check "exits 0 on an unparseable settings.json" exit_is "$status" 0
check "leaks no python traceback" not_contains "Traceback" "$out"

echo
echo "11. project identity:"
OTHER="$TMP/My_Other.Proj"
make_repo "$OTHER"
mkdir -p "$NOTES/projects/my-other-proj/facts"
write_fact "$NOTES/projects/my-other-proj/facts/other-fact.md" \
  other-fact project "belongs to the other project"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$OTHER" 2>&1)"
check "slugifies the repo basename (My_Other.Proj -> my-other-proj)" \
  contains "other-fact" "$out"
check "does not leak the other project's facts" not_contains "alpha-fact" "$out"

echo
echo "12. usage errors are loud, everything else is silent:"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --bogus 2>&1)"
status=$?
check "exits 2 on an unknown flag" exit_is "$status" 2
check "names the flag" contains "--bogus" "$out"

echo
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
