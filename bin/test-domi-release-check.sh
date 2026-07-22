#!/usr/bin/env bash
#
# test-domi-release-check.sh — exercise bin/domi-release-check.sh against
# throwaway fixture repos and a stub DomI checkout (#242). Never touches a
# real DomI-consumer repo or a real DomI checkout. The stub checker records
# its argv and cwd so forwarding is asserted verbatim, never narrated.
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRC="$REPO_ROOT/bin/domi-release-check.sh"

pass=0 fail=0
ok() {
  printf '  ✓ %s\n' "$1"
  pass=$((pass + 1))
}
bad() {
  printf '  ✗ %s\n' "$1"
  fail=$((fail + 1))
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FORTY="$(printf 'a%.0s' {1..40})" # 40 'a's — a valid-shaped SHA

# make_consumer <dir> <sha> — write a fixture consumer repo with a pin.
make_consumer() {
  local dir="$1" sha="$2"
  mkdir -p "$dir"
  cat >"$dir/.domi-pin" <<EOF
upstream: domattioli/DomI
branch: main
sha: $sha
manifest_sha256: $(printf 'b%.0s' {1..64})
pinned_at: 2026-07-13T00:00:00Z
EOF
}

# make_domi <dir> <exit-code> — write a stub DomI checkout whose
# release-integrity checker records argv + cwd and exits <exit-code>.
make_domi() {
  local dir="$1" rc="$2"
  mkdir -p "$dir/skills/release-integrity/scripts"
  cat >"$dir/skills/release-integrity/scripts/release_integrity.py" <<EOF
import os, sys
rec = os.environ["STUB_RECORD"]
with open(rec + "/argv", "w") as f:
    f.write("\n".join(sys.argv[1:]))
with open(rec + "/cwd", "w") as f:
    f.write(os.getcwd())
print("stub-domi-release-integrity ran")
if $rc != 0:
    print("stub-domi failure detail", file=sys.stderr)
sys.exit($rc)
EOF
}

# run_drc <target-repo> [env VAR=val ...] [-- <forwarded args ...>]
OUT=""
ERR=""
CODE=0
run_drc() {
  local target="$1"
  shift
  local envs=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    envs+=("$1")
    shift
  done
  OUT="$TMP/out"
  ERR="$TMP/err"
  env STUB_RECORD="$TMP/rec" "${envs[@]}" \
    bash "$DRC" --repo "$target" "$@" >"$OUT" 2>"$ERR"
  CODE=$?
}

mkdir -p "$TMP/rec"
# A fixture HOME with no installed skills, so real ~/.claude never leaks in.
BAREHOME="$TMP/barehome"
mkdir -p "$BAREHOME"

# --- not governed: no .domi-pin → exit 2 ---
mkdir -p "$TMP/plain"
run_drc "$TMP/plain" HOME="$BAREHOME" DOMI_LOCAL_CHECKOUT=/nonexistent
# shellcheck disable=SC2015
[ "$CODE" -eq 2 ] && grep -q "not-domi-governed" "$OUT" &&
  ok "no .domi-pin → not-domi-governed (exit 2)" ||
  bad "no .domi-pin → not-domi-governed (exit 2) [got $CODE]"

# --- malformed pin → exit 5, names the bad field ---
make_consumer "$TMP/badpin" "not-a-sha"
run_drc "$TMP/badpin" HOME="$BAREHOME" DOMI_LOCAL_CHECKOUT=/nonexistent
# shellcheck disable=SC2015
[ "$CODE" -eq 5 ] && grep -qi "malformed" "$ERR" &&
  ok "malformed pin → exit 5 naming the field" ||
  bad "malformed pin → exit 5 naming the field [got $CODE]"

# --- governed, checker unreachable → exit 4, explicit degraded outcome ---
make_consumer "$TMP/gov" "$FORTY"
run_drc "$TMP/gov" HOME="$BAREHOME" DOMI_LOCAL_CHECKOUT=/nonexistent
# shellcheck disable=SC2015
[ "$CODE" -eq 4 ] &&
  grep -q "checker-unreachable" "$OUT" &&
  grep -qi "degraded" "$OUT" &&
  grep -qi "not a pass" "$OUT" &&
  ok "governed, no checker → checker-unreachable (exit 4), degraded, never a pass" ||
  bad "governed, no checker → checker-unreachable (exit 4) [got $CODE]"

# --- governed, checker present via DOMI_LOCAL_CHECKOUT, DomI exits 0 → exit 0 ---
make_domi "$TMP/DomI-ok" 0
run_drc "$TMP/gov" HOME="$BAREHOME" DOMI_LOCAL_CHECKOUT="$TMP/DomI-ok"
# shellcheck disable=SC2015
[ "$CODE" -eq 0 ] &&
  grep -q "stub-domi-release-integrity ran" "$OUT" &&
  grep -q "domi-exit=0" "$OUT" &&
  grep -q "governed by domattioli/DomI@aaaaaaa" "$OUT" &&
  ok "checker runs clean → exit 0, output relayed, domi-exit=0 banner" ||
  bad "checker runs clean → exit 0, output relayed [got $CODE]"

# --- forwarded args reach the checker verbatim ---
rm -f "$TMP/rec/argv"
run_drc "$TMP/gov" HOME="$BAREHOME" DOMI_LOCAL_CHECKOUT="$TMP/DomI-ok" \
  -- --alpha "two words" beta
# shellcheck disable=SC2015
[ "$CODE" -eq 0 ] &&
  [ "$(cat "$TMP/rec/argv")" = "$(printf -- '--alpha\ntwo words\nbeta')" ] &&
  ok "args after -- forwarded to the checker verbatim" ||
  bad "args after -- forwarded verbatim [got $CODE, argv=$(tr '\n' '|' <"$TMP/rec/argv" 2>/dev/null)]"

# --- checker runs from the target repo's root, not the caller's cwd ---
rm -f "$TMP/rec/cwd"
(cd "$TMP" && env STUB_RECORD="$TMP/rec" HOME="$BAREHOME" \
  DOMI_LOCAL_CHECKOUT="$TMP/DomI-ok" \
  bash "$DRC" --repo "$TMP/gov" >"$TMP/out" 2>"$TMP/err")
CODE=$?
STUB_CWD="$(cat "$TMP/rec/cwd" 2>/dev/null)"
# resolve symlinks (macOS /tmp → /private/tmp) before comparing
WANT_CWD="$(cd "$TMP/gov" && pwd -P)"
GOT_CWD="$(cd "$STUB_CWD" 2>/dev/null && pwd -P)"
# shellcheck disable=SC2015
[ "$CODE" -eq 0 ] && [ "$GOT_CWD" = "$WANT_CWD" ] &&
  ok "checker cwd is the target repo root" ||
  bad "checker cwd is the target repo root [got $CODE, cwd=$STUB_CWD]"

# --- checker present, DomI exits nonzero → exit 6, its exit relayed ---
make_domi "$TMP/DomI-fail" 3
run_drc "$TMP/gov" HOME="$BAREHOME" DOMI_LOCAL_CHECKOUT="$TMP/DomI-fail"
# shellcheck disable=SC2015
[ "$CODE" -eq 6 ] &&
  grep -q "domi-exit=3" "$OUT" &&
  grep -q "stub-domi failure detail" "$ERR" &&
  ok "checker exits 3 → helper exit 6, domi-exit=3 banner, stderr relayed" ||
  bad "checker exits 3 → helper exit 6, domi-exit=3 [got $CODE]"

# --- env set but invalid: no silent fallback to defaults ---
# Build a home whose installed-skill symlink WOULD resolve, then prove an
# explicit DOMI_LOCAL_CHECKOUT=/nonexistent still wins (exclusive semantics).
LINKHOME="$TMP/linkhome"
mkdir -p "$LINKHOME/.claude/skills"
ln -s "$TMP/DomI-ok/skills/release-integrity" "$LINKHOME/.claude/skills/release-integrity"
run_drc "$TMP/gov" HOME="$LINKHOME" DOMI_LOCAL_CHECKOUT=/nonexistent
# shellcheck disable=SC2015
[ "$CODE" -eq 4 ] && grep -q "checker-unreachable" "$OUT" &&
  ok "DOMI_LOCAL_CHECKOUT set but invalid → no fallback, exit 4" ||
  bad "DOMI_LOCAL_CHECKOUT set but invalid → no fallback, exit 4 [got $CODE]"

# --- discovery via installed-skill symlink when env is unset ---
run_drc "$TMP/gov" HOME="$LINKHOME"
# shellcheck disable=SC2015
[ "$CODE" -eq 0 ] && grep -q "stub-domi-release-integrity ran" "$OUT" &&
  ok "env unset → checker found via ~/.claude/skills/release-integrity symlink" ||
  bad "env unset → found via installed-skill symlink [got $CODE]"

# --- discovery via sibling ../DomI of the target repo when env is unset ---
mkdir -p "$TMP/sib"
make_consumer "$TMP/sib/repo" "$FORTY"
make_domi "$TMP/sib/DomI" 0
run_drc "$TMP/sib/repo" HOME="$BAREHOME"
# shellcheck disable=SC2015
[ "$CODE" -eq 0 ] && grep -q "stub-domi-release-integrity ran" "$OUT" &&
  ok "env unset → checker found via target-sibling ../DomI" ||
  bad "env unset → found via target-sibling ../DomI [got $CODE]"

# --- usage: unknown flag → 64 ---
bash "$DRC" --bogus >"$TMP/out" 2>"$TMP/err"
CODE=$?
# shellcheck disable=SC2015
[ "$CODE" -eq 64 ] && grep -q "unknown argument" "$TMP/err" &&
  ok "unknown flag --bogus → usage error (exit 64)" ||
  bad "unknown flag --bogus → usage error (exit 64) [got $CODE]"

# --- usage: --repo with no value → 64 (guard against hang) ---
if command -v timeout >/dev/null 2>&1; then
  timeout 5 bash "$DRC" --repo >"$TMP/out" 2>"$TMP/err"
  CODE=$?
else
  bash "$DRC" --repo >"$TMP/out" 2>"$TMP/err" &
  pid=$!
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    CODE=124
  else
    wait "$pid"
    CODE=$?
  fi
fi
# shellcheck disable=SC2015
[ "$CODE" -eq 64 ] && grep -q "requires a path" "$TMP/err" &&
  ok "--repo no value → usage error (exit 64)" ||
  bad "--repo no value → usage error (exit 64) [got $CODE]"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
