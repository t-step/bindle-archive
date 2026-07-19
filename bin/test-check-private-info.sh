#!/usr/bin/env bash
#
# test-check-private-info.sh — carry bin/check-private-info.sh's --self-test
# into the discovered-suite gate, and prove that self-test is itself failable.
#
# The scanner's self-test is what proves the pattern rules still catch a relay
# email, a home path, a vault path, a transcript, and a denylist term. Before
# #279 it ran at exactly ONE call site — bin/check.sh section 7, inside the
# `if ! $content_only` branch — so only a full local `make check` reached it.
# The `bindle-private-info` hook runs the SCAN, never the self-test; CI runs
# `pre-commit run --all-files`, which inherits exactly that. So a regression in
# the scanner's own rules landed green. Same defect class as #256/#257: a real
# test that never reached the gate because it lived inside an aggregate script
# instead of being discoverable.
#
# This suite is discovered by `bindle-test-suites` (#256, #257), so the
# self-test now reaches the commit gate and CI with no registration edit.
# check.sh section 7 still calls `--self-test` directly and this suite calls
# the same entrypoint: one code path, two callers, so they cannot silently
# diverge. Neither runs a second full-tree scan — the tree sweep stays with
# check.sh section 7 and the `bindle-private-info` hook.
#
# Usage: bin/test-check-private-info.sh
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so a fixture git call would
# hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCANNER="$REPO_ROOT/bin/check-private-info.sh"

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

# shellcheck disable=SC2329 # invoked indirectly, by name, via check
contains() { grep -qF -- "$1" <<<"$2"; } # contains NEEDLE HAYSTACK

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ===========================================================================
echo "scanner self-test reaches this gate:"

selftest_out="$("$SCANNER" --self-test 2>&1)"
selftest_rc=$?

check "bin/check-private-info.sh --self-test exits clean" [ "$selftest_rc" -eq 0 ]
check "reports the scanner catches fixtures and passes clean files" \
  contains "scanner catches all fixtures, passes clean files" "$selftest_out"

# ===========================================================================
echo "self-test coverage floor:"

# The self-test prints "  self-test: <behaved>/<total> fixtures behaved". A
# fixture deleted from the self-test lowers <total> while the exit code stays
# 0 — coverage can shrink silently. Assert every fixture behaved AND that the
# fixture count has not dropped below what #268 left in place. Raise FLOOR
# when fixtures are added; never lower it to make a red suite green.
FLOOR=16
counts="$(sed -n 's|.*self-test: \([0-9]\{1,\}\)/\([0-9]\{1,\}\) fixtures behaved.*|\1 \2|p' <<<"$selftest_out")"
behaved="${counts% *}"
total="${counts#* }"

check "self-test reports a fixture count" [ -n "$counts" ]
check "every fixture behaved ($behaved/$total)" [ "$behaved" = "$total" ]
check "fixture coverage has not shrunk (>= $FLOOR)" [ "${total:-0}" -ge "$FLOOR" ]

# ===========================================================================
echo "self-test is failable:"

# A gate that cannot go red is decoration. Each case copies the scanner into a
# throwaway tree, breaks ONE rule, and requires the self-test to notice —
# proving the assertions above are load-bearing, not just a clean exit code.
# The copy sits at <dir>/bin/ because the scanner derives its own repo root
# from its location. --self-test returns before any git call, so no fixture
# repo is needed.
mutate() { # mutate NAME SED_EXPR EXPECTED_FAILURE_TEXT
  local name="$1" expr="$2" expected="$3" d="$TMP/$1" out rc
  mkdir -p "$d/bin"
  sed "$expr" "$SCANNER" >"$d/bin/check-private-info.sh"
  chmod +x "$d/bin/check-private-info.sh"

  if cmp -s "$SCANNER" "$d/bin/check-private-info.sh"; then
    printf '  ✗ %s (mutation changed nothing — the sed expression is stale)\n' "$name"
    fail=$((fail + 1))
    return
  fi

  out="$("$d/bin/check-private-info.sh" --self-test 2>&1)"
  rc=$?
  check "$name — self-test goes red" [ "$rc" -ne 0 ]
  check "$name — names the rule that broke" contains "$expected" "$out"
}

# The relay-email pattern stops matching: relay.md must no longer be flagged.
mutate "neutered apple-private-relay pattern" \
  's|privaterelay\\\.appleid|privaterelay-NEVERMATCH\\.appleid|' \
  "relay.md NOT flagged"

# Denylist matching loses case-insensitivity: 'Dana' stops catching 'dana'.
# shellcheck disable=SC2016 # "$term" is literal sed replacement text, not expansion
mutate "case-sensitive denylist matching" \
  's|grep -InFi "\$term"|grep -InF "$term"|' \
  "casefold.md NOT flagged"

# The clean verdict stops disclosing that NO denylist was loaded — the two
# facts ("nothing matched" vs "nothing was checked") collapse into one line.
mutate "clean verdict stops disclosing an absent denylist" \
  's|pattern rules only — NO personal denylist loaded|no personal denylist loaded|' \
  "does not disclose that NO denylist was loaded"

# ===========================================================================
echo
if [ "$fail" -eq 0 ]; then
  printf '  ✓ all %d checks pass\n' "$pass"
  exit 0
fi
printf '  %d of %d checks FAILED\n' "$fail" "$((pass + fail))"
exit 1
