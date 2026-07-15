#!/usr/bin/env bash
#
# test-issue-dedup-scan.sh — exercise bin/issue-dedup-scan.sh against a
# throwaway git fixture with an injected fake `gh` (never touches the network
# or a real repo). Proves the honest-by-construction guarantee: a failed
# sub-query yields `uncertain` (exit 4), distinct from an empty scan (exit 0).
#
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCAN="$REPO_ROOT/bin/issue-dedup-scan.sh"

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

# fixture git repo with one unrelated commit
FIX="$TMP/repo"
mkdir -p "$FIX"
git -C "$FIX" init -q
git -C "$FIX" config user.email t@e.st
git -C "$FIX" config user.name t
: >"$FIX/f"
git -C "$FIX" add f
git -C "$FIX" commit -qm "chore: seed unrelated commit"

# make_gh <mode> — write a fake gh into $TMP/bin that behaves per mode.
#   empty  : all subcommands succeed, emit []
#   haspr  : `pr list` emits one matching PR; others []
#   fail   : any invocation exits 1 (simulates network/tool failure)
make_gh() {
  local mode="$1"
  mkdir -p "$TMP/bin"
  cat >"$TMP/bin/gh" <<EOF
#!/usr/bin/env bash
mode="$mode"
if [ "\$mode" = fail ]; then exit 1; fi
case "\$1 \$2" in
  "pr list")
    if [ "\$mode" = haspr ]; then
      echo '[{"number":42,"title":"prior work #123","state":"MERGED","url":"u"}]'
    else echo '[]'; fi ;;
  "issue view") echo '{"comments":[]}' ;;
  *) echo '[]' ;;
esac
EOF
  chmod +x "$TMP/bin/gh"
}

run() { # run <issue#> <ghmode> ; sets $code and $out
  make_gh "$2"
  out="$(cd "$FIX" && GH="$TMP/bin/gh" "$SCAN" "$1" 2>/dev/null)"
  code=$?
}

# 1. clean repo, all queries succeed empty -> no-evidence / exit 0
run 123 empty
if [ "$code" -eq 0 ] && printf '%s' "$out" | grep -q '"verdict": "no-evidence"'; then
  ok "empty scan -> no-evidence (exit 0)"
else bad "empty scan: code=$code out=$out"; fi

# 2. a merged PR references the issue -> evidence-found / exit 3
run 123 haspr
if [ "$code" -eq 3 ] && printf '%s' "$out" | grep -q '"verdict": "evidence-found"'; then
  ok "matching PR -> evidence-found (exit 3)"
else bad "haspr: code=$code out=$out"; fi

# 3. a git commit references the issue -> evidence-found / exit 3
git -C "$FIX" commit -q --allow-empty -m "fix(#777): prior commit"
run 777 empty
if [ "$code" -eq 3 ]; then
  ok "matching commit -> evidence-found (exit 3)"
else bad "commit-evidence: code=$code out=$out"; fi

# 4. a sub-query FAILS -> uncertain / exit 4 (never no-evidence)
run 999 fail
if [ "$code" -eq 4 ] && printf '%s' "$out" | grep -q '"verdict": "uncertain"'; then
  ok "gh failure -> uncertain (exit 4), NOT no-evidence"
else bad "fail-closed: code=$code out=$out"; fi

# 5. usage error -> exit 64
(cd "$FIX" && "$SCAN" >/dev/null 2>&1)
# shellcheck disable=SC2015
[ $? -eq 64 ] &&
  ok "no arg -> usage error (exit 64)" || bad "usage error not 64"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
