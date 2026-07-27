#!/usr/bin/env bash
#
# test-run-test-suites.sh — suite for bin/run-test-suites.sh's failure
# reporting (#470).
#
# The runner discovered, ran and *scored* 38 suites without a suite of its own.
# That gap has a cost with a name: on 2026-07-26 a full run reported
#
#   1 of 37 suites FAILED:
#     bin/test-package-release-integrity.sh
#
# and nothing else. The runner captures each suite's output to
# "$workdir/$idx.log", never prints it, and deletes the whole workdir in an EXIT
# trap — so the only artifact of a red run is the suite's NAME plus the hint
# "re-run a failing suite directly to see its output". For a flake, re-running
# directly is exactly what makes the evidence disappear: the suite passed twice
# immediately afterwards on identical content, and the failure was never seen.
#
# So the contract asserted here is: a red run leaves EVIDENCE, not a hint.
# Every assertion below carries its own floor folded into the SAME predicate
# (present_and_absent / nonempty_and_absent), because a bare not_contains on a
# runner that produced no output at all passes vacuously — the #467/#472 shape,
# and this suite exists to catch a reporting gap, which is precisely the kind of
# thing a vacuous negative hides.
#
# Usage: bin/test-run-test-suites.sh
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge) git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so the fixture's `git init`
# and `git add` would reach the real repository. Scrub the hook environment —
# this suite's whole method is a throwaway git repo with fake suites in it.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$REPO_ROOT/bin/run-test-suites.sh"

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
# shellcheck disable=SC2329 # invoked indirectly, by name, via check
equals() { [ "$1" = "$2" ]; } # equals EXPECTED ACTUAL

# A bare not_contains passes VACUOUSLY whenever the runner produced nothing at
# all, which is the one outcome this suite must never score as a pass. Both
# negative forms below therefore floor themselves in the same predicate.
# shellcheck disable=SC2329 # invoked indirectly, by name, via check
present_and_absent() { # present_and_absent FLOOR NEEDLE HAYSTACK
  grep -qF -- "$1" <<<"$3" && ! grep -qF -- "$2" <<<"$3"
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The primary checkout must be untouched by every fixture below. Captured here,
# compared at the end: a fixture that escapes its sandbox moves one of these.
#
# Deliberately NOT a whole-repo `for-each-ref | wc -l` count, which is the guard
# bin/test-check-pressure-series.sh:81 and bin/test-check-gitleaks.sh:59 use.
# That number is global state, not sandbox state: it counts refs/remotes/* too,
# so an unrelated `git fetch`, a concurrent session, or the operator running
# `git checkout -b` while the suite is mid-flight all redden it. It reddened for
# exactly that reason while this suite was being written — a branch created two
# seconds into the run — which is the same disease as #470 rather than a
# sandbox breach. HEAD plus the porcelain status are sensitive to what an escape
# would actually do here (a stray `git add`/`git init` reaching the real repo,
# via a leaked GIT_DIR) and indifferent to legitimate ref churn.
GUARD_HEAD_BEFORE="$(git -C "$REPO_ROOT" rev-parse HEAD)"
GUARD_STATUS_BEFORE="$(git -C "$REPO_ROOT" status --porcelain)"

# make_fixture <name> — a throwaway repo carrying a COPY of the real runner at
# the same relative path, so its own REPO_ROOT/BASH_SOURCE resolution and its
# `git ls-files 'bin/test-*.sh'` discovery both land inside the fixture.
make_fixture() {
  local d="$TMP/$1"
  mkdir -p "$d/bin"
  cp "$RUNNER" "$d/bin/run-test-suites.sh"
  chmod +x "$d/bin/run-test-suites.sh"
  git -C "$d" init -q
  printf '%s\n' "$d"
}

# add_suite <dir> <name> <exit-code> <marker> — a fake suite that prints a
# unique marker on both streams and exits as told.
add_suite() {
  local d="$1" name="$2" rc="$3" marker="$4"
  cat >"$d/bin/$name" <<EOF
#!/usr/bin/env bash
echo "$marker-stdout"
echo "$marker-stderr" >&2
exit $rc
EOF
  chmod +x "$d/bin/$name"
  git -C "$d" add "bin/$name" >/dev/null 2>&1
}

echo "all-pass run:"
FIX="$(make_fixture allpass)"
add_suite "$FIX" "test-alpha.sh" 0 "ALPHAMARK"
add_suite "$FIX" "test-beta.sh" 0 "BETAMARK"
out="$("$FIX/bin/run-test-suites.sh" 2>&1)"
rc=$?
check "all-pass run exits 0" equals "0" "$rc"
check "all-pass run reports the count" contains "all 2 suites pass" "$out"
# The pass path must stay quiet: dumping every passing suite's output would bury
# the one that matters. Floored on the summary line, so a runner that printed
# nothing cannot satisfy it.
check "a passing suite's output is not dumped" \
  present_and_absent "all 2 suites pass" "ALPHAMARK-stdout" "$out"

echo "one failing suite:"
FIX="$(make_fixture onefail)"
add_suite "$FIX" "test-alpha.sh" 0 "ALPHAMARK"
add_suite "$FIX" "test-broken.sh" 1 "BROKENMARK"
out="$("$FIX/bin/run-test-suites.sh" 2>&1)"
rc=$?
check "failing run exits 1" equals "1" "$rc"
check "failing run still names the suite" contains "bin/test-broken.sh" "$out"
# The #470 contract. Both streams, because a suite's diagnosis is as likely to
# be on stderr as on stdout, and the runner merges them into one log.
check "the failing suite's stdout is printed" contains "BROKENMARK-stdout" "$out"
check "the failing suite's stderr is printed" contains "BROKENMARK-stderr" "$out"
# Attribution: an unlabelled dump beside a list of names is unreadable the
# moment two suites fail.
check "the printed output is attributed to its suite" \
  contains "output: bin/test-broken.sh" "$out"
check "a passing suite's output is still not dumped" \
  present_and_absent "BROKENMARK-stdout" "ALPHAMARK-stdout" "$out"

echo "two failing suites:"
FIX="$(make_fixture twofail)"
add_suite "$FIX" "test-alpha.sh" 0 "ALPHAMARK"
add_suite "$FIX" "test-broken.sh" 1 "BROKENMARK"
add_suite "$FIX" "test-worse.sh" 3 "WORSEMARK"
out="$("$FIX/bin/run-test-suites.sh" 2>&1)"
rc=$?
check "two failures exit 1" equals "1" "$rc"
check "both failing suites' output is printed" \
  contains "BROKENMARK-stdout" "$out"
check "the second failing suite's output is printed too" \
  contains "WORSEMARK-stdout" "$out"

echo "a failing suite that printed nothing:"
FIX="$(make_fixture silentfail)"
cat >"$FIX/bin/test-silent.sh" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$FIX/bin/test-silent.sh"
git -C "$FIX" add bin/test-silent.sh >/dev/null 2>&1
out="$("$FIX/bin/run-test-suites.sh" 2>&1)"
# A suite that fails silently is its own finding — the runner must say so
# rather than printing an empty block that reads like a missing feature.
check "an empty log is reported as empty, not omitted" \
  contains "no output" "$out"

echo "a long log is bounded, and the bound is disclosed:"
FIX="$(make_fixture longlog)"
cat >"$FIX/bin/test-verbose.sh" <<'EOF'
#!/usr/bin/env bash
echo "FIRSTLINEMARK"
i=0
while [ "$i" -lt 200 ]; do
  echo "filler line $i"
  i=$((i + 1))
done
echo "LASTLINEMARK"
exit 1
EOF
chmod +x "$FIX/bin/test-verbose.sh"
git -C "$FIX" add bin/test-verbose.sh >/dev/null 2>&1
out="$("$FIX/bin/run-test-suites.sh" 2>&1)"
# The tail must actually be a tail: the last line present, the first line gone.
# Folded, so a runner that printed no log at all cannot score this as a pass —
# which is the exact state this whole suite exists to distinguish from success.
check "a long log is truncated to its tail" \
  present_and_absent "LASTLINEMARK" "FIRSTLINEMARK" "$out"
# A silent cap reads as "you saw everything". Disclose the withheld count and
# where the full text lives, or the truncation is itself a reporting gap.
check "the truncation discloses how much it withheld" \
  contains "showing the last 40 of 202 lines" "$out"
check "the truncation names a readable full log" contains "full log: " "$out"
check "the retained log directory is named" contains "failing logs kept: " "$out"
# The full log has to survive the runner's EXIT trap, or the disclosure above
# points at a path that no longer exists — a hint dressed up as evidence.
kept="$(sed -n 's/.*failing logs kept: //p' <<<"$out" | head -1)"
check "the retained full log exists after the run" test -s "$kept/test-verbose.log"
check "the retained log is complete, not the tail" \
  contains "FIRSTLINEMARK" "$(cat "$kept/test-verbose.log" 2>/dev/null)"
rm -rf "$kept"

# A seam reachable only through its env override leaves the DEFAULT untested
# (#246). The default is exercised by every case above; this is the override.
out="$(BINDLE_TEST_LOG_LINES=5 "$FIX/bin/run-test-suites.sh" 2>&1)"
check "BINDLE_TEST_LOG_LINES changes the bound" \
  contains "showing the last 5 of 202 lines" "$out"
kept="$(sed -n 's/.*failing logs kept: //p' <<<"$out" | head -1)"
rm -rf "$kept"

echo "a non-executable suite:"
FIX="$(make_fixture notexec)"
cat >"$FIX/bin/test-inert.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod -x "$FIX/bin/test-inert.sh"
git -C "$FIX" add bin/test-inert.sh >/dev/null 2>&1
out="$("$FIX/bin/run-test-suites.sh" 2>&1)"
rc=$?
check "a non-executable suite fails the run" equals "1" "$rc"
check "a non-executable suite is named as such" contains "not executable" "$out"

echo "sandbox guard:"
GUARD_HEAD_AFTER="$(git -C "$REPO_ROOT" rev-parse HEAD)"
GUARD_STATUS_AFTER="$(git -C "$REPO_ROOT" status --porcelain)"
check "no fixture moved the primary checkout's HEAD" \
  equals "$GUARD_HEAD_BEFORE" "$GUARD_HEAD_AFTER"
check "no fixture touched the primary checkout's index or worktree" \
  equals "$GUARD_STATUS_BEFORE" "$GUARD_STATUS_AFTER"

echo "test-run-test-suites: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
