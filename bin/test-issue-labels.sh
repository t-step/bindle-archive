#!/usr/bin/env bash
#
# test-issue-labels.sh — self-test for bin/check-issue-labels.sh.
#
# Hermetic: a stub `gh` on PATH answers from canned JSON, so no case here
# reaches the network. The stub is also how the gh-unavailable path is
# exercised — the script must SKIP loudly and non-green, never report a
# silent pass it did not earn.
#
set -euo pipefail

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO_ROOT/bin/check-issue-labels.sh"
PASS=0
FAIL=0

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STUBBIN="$TMP/bin"
mkdir -p "$STUBBIN"

# Stub gh: `gh issue list ... --json ...` prints $GH_ISSUES; `gh label list`
# prints $GH_LABELS. GH_BROKEN=1 makes every call fail, standing in for an
# absent or unauthenticated gh.
cat >"$STUBBIN/gh" <<'STUB'
#!/usr/bin/env bash
[ "${GH_BROKEN:-0}" = "1" ] && exit 1
case "${1:-}" in
  issue) printf '%s' "${GH_ISSUES:-[]}" ;;
  label) printf '%s' "${GH_LABELS:-}" ;;
  auth) exit 0 ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$STUBBIN/gh"
export PATH="$STUBBIN:$PATH"

run() { # run -> prints output, sets RC
  set +e
  OUT="$(bash "$CHECK" 2>&1)"
  RC=$?
  set -e
}

check() { # check <want-rc> <name> [substring]
  local want="$1" name="$2" needle="${3:-}"
  local ok=1
  [ "$RC" = "$want" ] || ok=0
  if [ -n "$needle" ] && ! grep -qF -- "$needle" <<<"$OUT"; then ok=0; fi
  if [ "$ok" = 1 ]; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (rc=$RC wanted $want)" >&2
    awk '{print "      " $0}' <<<"$OUT" >&2
  fi
}

echo "check-issue-labels self-test"

# --- all three invariants hold ----------------------------------------------
export GH_ISSUES='[]'
export GH_LABELS='status: triage	Not yet assessed
priority: normal	Normal'
run
check 0 "clean repo passes" "no closed issue carries"

# --- invariant 1: a closed issue still carrying a status: label -------------
export GH_ISSUES='[{"number":287,"state":"CLOSED","labels":[{"name":"status: in-progress"}]}]'
run
check 1 "closed issue with status: label fails" "#287"

# --- invariant 2: an open non-triage issue with no priority -----------------
export GH_ISSUES='[{"number":197,"state":"OPEN","labels":[{"name":"status: ready"}]}]'
run
check 1 "open non-triage issue without priority fails" "#197"

export GH_ISSUES='[{"number":197,"state":"OPEN","labels":[{"name":"status: triage"}]}]'
run
check 0 "open TRIAGE issue without priority passes"

export GH_ISSUES='[{"number":197,"state":"OPEN","labels":[{"name":"status: ready"},{"name":"priority: now"}]}]'
run
check 0 "open issue with priority passes"

# --- invariant 3: the retired status: done label still exists ---------------
export GH_ISSUES='[]'
export GH_LABELS='status: done
status: triage	Not yet assessed'
run
check 1 "surviving 'status: done' label fails" "status: done"

# --- gh unavailable: skip LOUDLY, never a silent green ----------------------
export GH_LABELS='status: triage	Not yet assessed'
export GH_BROKEN=1
run
check 2 "gh unavailable skips loudly" "SKIPPED"
unset GH_BROKEN

echo
if [ "$FAIL" -gt 0 ]; then
  echo "  $PASS passed, $FAIL FAILED" >&2
  exit 1
fi
echo "  all $PASS checks pass"
