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

# --- dry-run: calls release-please with --dry-run + --token, mutates nothing ---
# GITHUB_TOKEN=faketoken so the real gh token is never used or logged by the stub.
out="$(cd "$FIX" && GITHUB_TOKEN=faketoken RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
  "$SEL" dry-run 2>&1)"
code=$?
after="$(snapshot)"
{
  [ "$code" -eq 0 ] &&
    grep -q -- '--dry-run' "$RP_STUB_LOG" &&
    grep -q -- '--token=faketoken' "$RP_STUB_LOG" &&
    grep -q 'release-pr' "$RP_STUB_LOG" &&
    [ "$before" = "$after" ]
} &&
  ok "dry-run assembles --dry-run + --token + mutates nothing" ||
  bad "dry-run ($code): log=$(cat "$RP_STUB_LOG"); mutated=$([ "$before" = "$after" ] && echo no || echo YES)"

# --- dry-run with no token available: hard stop (exit 4), no invocation ---
GHSTUB="$TMP/ghstub"
mkdir -p "$GHSTUB"
printf '#!/usr/bin/env bash\nexit 1\n' >"$GHSTUB/gh"
chmod +x "$GHSTUB/gh"
: >"$RP_STUB_LOG"
out="$(cd "$FIX" && PATH="$GHSTUB:$PATH" GITHUB_TOKEN='' RC_CONFIG="$TMP/good.toml" \
  RELEASE_PLEASE_CMD="$STUB" "$SEL" dry-run 2>&1)"
code=$?
{ [ "$code" -eq 4 ] && [ ! -s "$RP_STUB_LOG" ]; } &&
  ok "dry-run with no token -> exit 4, no invocation" ||
  bad "no-token ($code): log=$(cat "$RP_STUB_LOG")"

# --- apply without token: refuses, no invocation ---
: >"$RP_STUB_LOG"
out="$(cd "$FIX" && RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
  "$SEL" apply 2>&1)"
code=$?
{ [ "$code" -eq 3 ] && [ ! -s "$RP_STUB_LOG" ]; } &&
  ok "apply without token refuses, no invocation" ||
  bad "apply-no-token ($code): log=$(cat "$RP_STUB_LOG")"

# A stub release-please-sync.sh that records its argv and mutates nothing.
SYNC_STUB="$TMP/sync-stub.sh"
cat >"$SYNC_STUB" <<'EOF'
#!/usr/bin/env bash
echo "STUB-SYNC $*" >>"$SYNC_STUB_LOG"
echo "release-please-sync stub ok"
EOF
chmod +x "$SYNC_STUB"
export SYNC_STUB_LOG="$TMP/sync.log"

# --- apply with token: invokes release-please with --token, WITHOUT --dry-run,
# then chains release-please-sync.sh apply with the SAME token (#152) ---
: >"$RP_STUB_LOG"
: >"$SYNC_STUB_LOG"
out="$(cd "$FIX" && GITHUB_TOKEN=faketoken RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
  RELEASE_PLEASE_SYNC_CMD="$SYNC_STUB" \
  "$SEL" apply --approval-token "eph-123" 2>&1)"
code=$?
{
  [ "$code" -eq 0 ] &&
    grep -q 'release-pr' "$RP_STUB_LOG" &&
    grep -q -- '--token=faketoken' "$RP_STUB_LOG" &&
    ! grep -q -- '--dry-run' "$RP_STUB_LOG"
} &&
  ok "apply with token invokes release-pr (--token, no --dry-run)" ||
  bad "apply-token ($code): log=$(cat "$RP_STUB_LOG")"
{
  grep -q -- 'apply' "$SYNC_STUB_LOG" &&
    grep -q -- '--approval-token eph-123' "$SYNC_STUB_LOG"
} &&
  ok "apply chains release-please-sync.sh apply with the same token" ||
  bad "apply-chains-sync: log=$(cat "$SYNC_STUB_LOG")"

# --- apply: a failing chained sync fails the whole apply, no silent success ---
FAIL_SYNC_STUB="$TMP/sync-fail-stub.sh"
cat >"$FAIL_SYNC_STUB" <<'EOF'
#!/usr/bin/env bash
echo "sync stub: forced failure" >&2
exit 1
EOF
chmod +x "$FAIL_SYNC_STUB"
: >"$RP_STUB_LOG"
out="$(cd "$FIX" && GITHUB_TOKEN=faketoken RC_CONFIG="$TMP/good.toml" RELEASE_PLEASE_CMD="$STUB" \
  RELEASE_PLEASE_SYNC_CMD="$FAIL_SYNC_STUB" \
  "$SEL" apply --approval-token "eph-456" 2>&1)"
code=$?
[ "$code" -ne 0 ] &&
  ok "apply fails when the chained sync fails" ||
  bad "apply-sync-failure ($code): $out"

# --- Release Please config: simple type, component-less tag, manifest is semver ---
# The manifest version is NOT hardcoded — it advances every release (0.4.0 at
# seed, 0.5.0 after the first cut, ...); assert it's a valid semver, not a value.
CFG="$REPO_ROOT/release-please-config.json"
MAN="$REPO_ROOT/.release-please-manifest.json"
{ python3 -c "import json, re; c=json.load(open('$CFG')); \
    p=c['packages']['.']; assert p['release-type']=='simple', p; \
    assert c.get('include-component-in-tag') is False, c; \
    m=json.load(open('$MAN')); assert re.match(r'^[0-9]+\.[0-9]+\.[0-9]+\$', m['.']), m"; } &&
  ok "release-please config: simple type, component-less tag, manifest is semver" ||
  bad "release-please config invalid"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
