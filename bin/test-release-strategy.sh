#!/usr/bin/env bash
#
# test-release-strategy.sh — exercise bin/release-strategy.sh (the selector seam)
# and bin/release-strategies/local-release-please.sh against throwaway fixtures
# with a stubbed release-please. Never touches the network or a real repo.
#
# shellcheck disable=SC2015 # `cond && ok || bad` is the intended assertion idiom (bad only runs on failure); ok/bad never fail
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEL="$REPO_ROOT/bin/release-strategy.sh"

pass=0 fail=0
ok() {
  printf '  \342\234\223 %s\n' "$1"
  pass=$((pass + 1))
}
bad() {
  printf '  \342\234\227 %s\n' "$1"
  fail=$((fail + 1))
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

run() { # run <config-file> <args...> -> sets $code/$out
  local cfg="$1"
  shift
  out="$(RC_CONFIG="$cfg" "$SEL" "$@" 2>&1)"
  code=$?
}

# --- fail-closed: missing config ---
run "$TMP/nope.toml" which
{ [ "$code" -eq 64 ] && printf '%s' "$out" | grep -qi 'missing'; } &&
  ok "missing config -> exit 64" || bad "missing config ($code): $out"

# --- fail-closed: config present but no strategy key ---
: >"$TMP/empty.toml"
run "$TMP/empty.toml" which
[ "$code" -eq 64 ] && ok "no strategy key -> exit 64" || bad "no key ($code)"

# --- fail-closed: unknown strategy name ---
printf 'strategy = "does-not-exist"\n' >"$TMP/unknown.toml"
run "$TMP/unknown.toml" which
{ [ "$code" -eq 64 ] && printf '%s' "$out" | grep -qi 'unknown strategy'; } &&
  ok "unknown strategy -> exit 64" || bad "unknown strategy ($code): $out"

# --- which: resolves the real local-release-please strategy ---
printf 'strategy = "local-release-please"\n' >"$TMP/good.toml"
run "$TMP/good.toml" which
{ [ "$code" -eq 0 ] && printf '%s' "$out" | grep -q 'local-release-please'; } &&
  ok "which resolves strategy" || bad "which ($code): $out"

# --- unknown verb ---
run "$TMP/good.toml" bogus-verb
[ "$code" -eq 2 ] && ok "unknown verb -> exit 2" || bad "unknown verb ($code)"

# A stub release-please that records its argv and mutates NOTHING.
STUB="$TMP/rp-stub.sh"
cat >"$STUB" <<'EOF'
#!/usr/bin/env bash
echo "STUB-RELEASE-PLEASE $*" >>"$RP_STUB_LOG"
echo "release-please stub ok"
EOF
chmod +x "$STUB"

# A git fixture the strategy runs inside; we assert it stays byte-identical.
FIX="$TMP/fix"
git init -q "$FIX"
git -C "$FIX" config user.email t@e.st
git -C "$FIX" config user.name t
git -C "$FIX" checkout -q -b main
: >"$FIX/f"
git -C "$FIX" add f
git -C "$FIX" commit -qm base
git -C "$FIX" remote add origin https://example.invalid/o/r.git
snapshot() {
  git -C "$FIX" status --porcelain
  git -C "$FIX" rev-parse HEAD
}

export RP_STUB_LOG="$TMP/rp.log"
: >"$RP_STUB_LOG"
before="$(snapshot)"

# --- dry-run: calls release-please with --dry-run, mutates nothing ---
out="$(cd "$FIX" && RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
  "$SEL" dry-run 2>&1)"
code=$?
after="$(snapshot)"
{
  [ "$code" -eq 0 ] &&
    grep -q -- '--dry-run' "$RP_STUB_LOG" &&
    grep -q 'release-pr' "$RP_STUB_LOG" &&
    [ "$before" = "$after" ]
} &&
  ok "dry-run assembles --dry-run + mutates nothing" ||
  bad "dry-run ($code): log=$(cat "$RP_STUB_LOG"); mutated=$([ "$before" = "$after" ] && echo no || echo YES)"

# --- apply without token: refuses, no invocation ---
: >"$RP_STUB_LOG"
out="$(cd "$FIX" && RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
  "$SEL" apply 2>&1)"
code=$?
{ [ "$code" -eq 3 ] && [ ! -s "$RP_STUB_LOG" ]; } &&
  ok "apply without token refuses, no invocation" ||
  bad "apply-no-token ($code): log=$(cat "$RP_STUB_LOG")"

# --- apply with token: invokes release-please WITHOUT --dry-run ---
: >"$RP_STUB_LOG"
out="$(cd "$FIX" && RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
  "$SEL" apply --approval-token "eph-123" 2>&1)"
code=$?
{
  [ "$code" -eq 0 ] &&
    grep -q 'release-pr' "$RP_STUB_LOG" &&
    ! grep -q -- '--dry-run' "$RP_STUB_LOG"
} &&
  ok "apply with token invokes release-pr (no --dry-run)" ||
  bad "apply-token ($code): log=$(cat "$RP_STUB_LOG")"

# --- Release Please config: valid JSON, simple type, manifest seeded 0.4.0 ---
CFG="$REPO_ROOT/release-please-config.json"
MAN="$REPO_ROOT/.release-please-manifest.json"
{ python3 -c "import json; c=json.load(open('$CFG')); \
    p=c['packages']['.']; assert p['release-type']=='simple', p; \
    m=json.load(open('$MAN')); assert m['.']=='0.4.0', m"; } &&
  ok "release-please config: simple type, manifest seeded 0.4.0" ||
  bad "release-please config invalid"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
