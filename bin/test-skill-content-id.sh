#!/usr/bin/env bash
# Tests bin/skill-content-id.sh (#339): identity formula (tracked files under
# skills/<name>/ minus PRESSURE-TESTS.md, working-tree bytes, sorted), --check
# verdicts and exit codes, --all aggregation and _template skip.
set -uo pipefail

# Under a git hook, git exports GIT_DIR and friends to subprocesses; scrub so
# the fixture-repo git calls below cannot hit the real repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ID_SRC="$REPO_ROOT/bin/skill-content-id.sh"

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
exit_is() { [ "$1" -eq "$2" ]; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

build_fixture() { # build_fixture <dir> — a minimal repo with three skills
  local d="$1"
  mkdir -p "$d/bin" "$d/skills/demo/references" "$d/skills/_template" \
    "$d/skills/other"
  cp "$ID_SRC" "$d/bin/skill-content-id.sh"
  chmod +x "$d/bin/skill-content-id.sh"
  printf 'demo body v1\n' >"$d/skills/demo/SKILL.md"
  printf 'ref v1\n' >"$d/skills/demo/references/notes.md"
  printf 'evidence v1\n' >"$d/skills/demo/PRESSURE-TESTS.md"
  printf 'template\n' >"$d/skills/_template/SKILL.md"
  printf 'other body\n' >"$d/skills/other/SKILL.md"
  (cd "$d" && git init -q && git add -A &&
    git -c user.email=t@t -c user.name=t commit -qm init)
}

echo "identity formula:"

FIX="$TMP/fix1"
build_fixture "$FIX"
id1="$(cd "$FIX" && bin/skill-content-id.sh demo)"
id2="$(cd "$FIX" && bin/skill-content-id.sh demo)"
case "$id1" in
  sha256:????????????) check "prints a sha256:<12 hex> id" true ;;
  *) check "prints a sha256:<12 hex> id" false ;;
esac
check "id is stable across runs" test "$id1" = "$id2"

printf 'evidence v2\n' >"$FIX/skills/demo/PRESSURE-TESTS.md"
id3="$(cd "$FIX" && bin/skill-content-id.sh demo)"
check "PRESSURE-TESTS.md edits do not change the id" test "$id1" = "$id3"

printf 'ref v2\n' >"$FIX/skills/demo/references/notes.md"
id4="$(cd "$FIX" && bin/skill-content-id.sh demo)"
check "references/ edits change the id" test "$id1" != "$id4"
printf 'ref v1\n' >"$FIX/skills/demo/references/notes.md"

printf 'untracked scratch\n' >"$FIX/skills/demo/scratch.md"
id5="$(cd "$FIX" && bin/skill-content-id.sh demo)"
check "untracked files do not change the id" test "$id1" = "$id5"
rm "$FIX/skills/demo/scratch.md"

printf 'demo body v2\n' >"$FIX/skills/demo/SKILL.md"
id6="$(cd "$FIX" && bin/skill-content-id.sh demo)"
check "uncommitted working-tree SKILL.md edits change the id" \
  test "$id1" != "$id6"
printf 'demo body v1\n' >"$FIX/skills/demo/SKILL.md"

rm "$FIX/skills/demo/references/notes.md"
(cd "$FIX" && bin/skill-content-id.sh demo >/dev/null 2>&1)
rc=$?
check "tracked file missing from working tree fails loudly (exit 3)" \
  exit_is "$rc" 3
printf 'ref v1\n' >"$FIX/skills/demo/references/notes.md"

(cd "$FIX" && bin/skill-content-id.sh nonexistent >/dev/null 2>&1)
rc=$?
check "unknown skill (no tracked files) is exit 2" exit_is "$rc" 2

echo "--check verdicts:"

FIX2="$TMP/fix2"
build_fixture "$FIX2"
cur="$(cd "$FIX2" && bin/skill-content-id.sh demo)"

out="$(cd "$FIX2" && bin/skill-content-id.sh --check demo)"
rc=$?
check "no hashed series is exit 2" exit_is "$rc" 2
check "verdict names NO-HASHED-SERIES" contains "NO-HASHED-SERIES" "$out"

printf '%s\n' "**Content:** unrecorded" >"$FIX2/skills/demo/PRESSURE-TESTS.md"
out="$(cd "$FIX2" && bin/skill-content-id.sh --check demo)"
rc=$?
check "unrecorded-only series is still exit 2" exit_is "$rc" 2

printf '%s\n%s\n' "**Content:** sha256:000000000000" "**Content:** $cur" \
  >"$FIX2/skills/demo/PRESSURE-TESTS.md"
out="$(cd "$FIX2" && bin/skill-content-id.sh --check demo)"
rc=$?
check "newest (last-in-file) hashed line matching is FRESH exit 0" \
  exit_is "$rc" 0
check "per-line report marks the stale older series" \
  contains "sha256:000000000000 STALE" "$out"

printf '%s\n%s\n' "**Content:** $cur" "**Content:** sha256:000000000000" \
  >"$FIX2/skills/demo/PRESSURE-TESTS.md"
out="$(cd "$FIX2" && bin/skill-content-id.sh --check demo)"
rc=$?
check "newest hashed line differing is STALE exit 1" exit_is "$rc" 1
check "verdict names the newest recorded id" \
  contains "newest hashed series sha256:000000000000" "$out"

echo "--check --all:"

out="$(cd "$FIX2" && bin/skill-content-id.sh --check --all)"
rc=$?
check "aggregate exit is 1 when any skill is stale" exit_is "$rc" 1
check "the stale skill is named" contains "demo: STALE" "$out"
check "_template is skipped" not_contains "_template" "$out"
check "no-hashed-series skills are reported, not fatal" \
  contains "other: NO-HASHED-SERIES" "$out"

printf '%s\n' "**Content:** $cur" >"$FIX2/skills/demo/PRESSURE-TESTS.md"
out="$(cd "$FIX2" && bin/skill-content-id.sh --check --all)"
rc=$?
check "aggregate exit is 0 when nothing is stale" exit_is "$rc" 0

echo "usage:"

(cd "$FIX2" && bin/skill-content-id.sh >/dev/null 2>&1)
rc=$?
check "no args is usage error 64" exit_is "$rc" 64
(cd "$FIX2" && bin/skill-content-id.sh --all >/dev/null 2>&1)
rc=$?
check "--all without --check is usage error 64" exit_is "$rc" 64

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
