#!/usr/bin/env bash
#
# test-check-gitleaks.sh — prove bin/check-gitleaks.sh's two modes see
# different things, disclose their scope, and never report a skipped scan as
# clean (#354).
#
# The gate exists because gitleaks was installed, verified (#259) and wired
# into nothing. The design call it encodes: a history scan is blind to STAGED
# content, because staged content is not yet a commit. So a gate wired only
# into `make check` would have read clean on PR #345's three home-path hits at
# the moment they were staged — rebuilding the #347 hole rather than closing
# it. `--staged` (the pre-commit hook) and `--history` (make check) therefore
# cover different populations, and the pair of assertions in "the two modes are
# not redundant" is what keeps a later simplification from collapsing them.
#
# Every fixture is a throwaway repo under $TMP. The synthetic secret is
# ASSEMBLED AT RUNTIME from fragments so this tracked file carries no matchable
# secret of its own — otherwise the suite would need a .gitleaks.toml allowlist
# entry, re-introducing exactly the private-ok/allowlist asymmetry #354's
# design declined to automate.
#
# Usage: bin/test-check-gitleaks.sh
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so a fixture git call would
# hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$REPO_ROOT/bin/check-gitleaks.sh"

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
not_contains() { ! grep -qF -- "$1" <<<"$2"; } # not_contains NEEDLE HAYSTACK
# shellcheck disable=SC2329 # invoked indirectly, by name, via check
equals() { [ "$1" = "$2" ]; } # equals EXPECTED ACTUAL

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The primary checkout must be untouched by every fixture below. Captured here,
# compared at the end: a fixture that escapes its sandbox moves one of these.
GUARD_REFS_BEFORE="$(git -C "$REPO_ROOT" for-each-ref | wc -l | tr -d ' ')"
GUARD_HEAD_BEFORE="$(git -C "$REPO_ROOT" rev-parse HEAD)"

# A secret gitleaks' default ruleset matches, assembled so no fragment in this
# file is itself a finding. AWS is used because it is in the built-in ruleset
# `useDefault = true` pulls in, so the fixture does not depend on Bindle's own
# added rules.
#
# DO NOT replace this with AWS's canonical `AKIAIOSFODNN7EXAMPLE`. That key is
# published documentation and gitleaks' default config stopwords it, so a
# fixture built on it is scanned clean — the assertions still "pass" (a missing
# or broken gate also exits non-zero) while measuring nothing at all. Verified
# 2026-07-26: `gitleaks git .` on a fixture whose HEAD commit contained that key
# reported `no leaks found`, rc 0. Any replacement key must be re-verified the
# same way before it is trusted.
synthetic_secret() {
  printf 'aws_access_key_id = "%s%s"\n' 'AKIA' 'QYLPMN5HGXV2TZ4W'
}

new_fixture() { # new_fixture NAME -> prints its path
  local dir="$TMP/$1"
  mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" config user.email t@e.st
  git -C "$dir" config user.name tester
  git -C "$dir" config commit.gpgsign false
  printf 'placeholder\n' >"$dir/README.md"
  git -C "$dir" add README.md
  git -C "$dir" commit -qm "initial"
  printf '%s\n' "$dir"
}

# Sections that need a real gitleaks are gated on having one. The gate itself
# exits 0 with a NOT RUN notice when the binary is absent, so a suite that went
# red in that situation would block every commit on a machine that never
# installed an OPTIONAL tool — contradicting the behavior it is here to protect.
# The absent-binary and argument-handling sections need no binary and always
# run.
HAVE_GITLEAKS=true
command -v gitleaks >/dev/null 2>&1 || HAVE_GITLEAKS=false

# ===========================================================================
if ! $HAVE_GITLEAKS; then
  echo "scan behavior: SKIPPED — gitleaks is not installed on this machine."
  echo "  the absent-binary and argument sections below still run."
fi

if $HAVE_GITLEAKS; then
  echo "a planted secret reddens the gate:"

  fx="$(new_fixture planted)"
  synthetic_secret >"$fx/creds.txt"
  git -C "$fx" add creds.txt
  staged_out="$(cd "$fx" && "$GATE" --staged 2>&1)"
  staged_rc=$?

  check "--staged exits non-zero on a staged secret" \
    [ "$staged_rc" -ne 0 ]
  check "--staged names the offending file" \
    contains "creds.txt" "$staged_out"
  check "--staged does not call a red run clean" \
    not_contains "no leaks" "$staged_out"

  # ===========================================================================
  echo
  echo "the two modes are not redundant (the #345 shape):"
  #
  # Same fixture, same instant: the secret is staged and NOT committed. This is
  # the exact state PR #345 was in when a history-only scan reported clean.

  history_out="$(cd "$fx" && "$GATE" --history 2>&1)"
  history_rc=$?

  check "--history exits 0 while the secret is only staged" \
    [ "$history_rc" -eq 0 ]
  check "--history does not silently pass — it discloses the staged file" \
    contains "creds.txt" "$history_out"
  check "--history's clean verdict is qualified by a PARTIAL banner" \
    contains "PARTIAL" "$history_out"

  # ===========================================================================
  echo
  echo "a secret already in history reddens --history:"

  fx2="$(new_fixture committed)"
  synthetic_secret >"$fx2/creds.txt"
  git -C "$fx2" add creds.txt
  git -C "$fx2" commit -qm "add creds"
  hist2_out="$(cd "$fx2" && "$GATE" --history 2>&1)"
  hist2_rc=$?

  check "--history exits non-zero on a committed secret" \
    [ "$hist2_rc" -ne 0 ]
  check "--history reports the commit count it scanned" \
    contains "commit" "$hist2_out"

  # ===========================================================================
  echo
  echo "the reported count is what gitleaks scanned, not what git counted:"
  #
  # The scope line is a claim about what was examined, so it must come from the
  # scanner, not from a proxy that merely looks similar. `git rev-list --count`
  # is the tempting proxy and it is WRONG: gitleaks counts commits it actually
  # read a patch from, so an empty commit is counted by git and not by gitleaks.
  # On this repo the two read 758 vs 523.
  #
  # The fixture is built so the forbidden reading gives a DIFFERENT answer —
  # 3 commits by rev-list, 1 scanned — otherwise the assertion would pass under
  # either implementation and prove nothing.

  fx4="$(new_fixture counting)"
  git -C "$fx4" commit -q --allow-empty -m "empty two"
  git -C "$fx4" commit -q --allow-empty -m "empty three"
  count_out="$(cd "$fx4" && "$GATE" --history 2>&1)"
  revlist_n="$(git -C "$fx4" rev-list --count HEAD)"
  # gitleaks' own figure, taken from gitleaks itself rather than parsed back out
  # of the gate's output — on a green run the gate prints its verdict, not the
  # scanner's log, and a test that reads its subject's paraphrase of a number is
  # not checking that number at all.
  gitleaks_n="$(cd "$fx4" && gitleaks git . --redact --no-banner 2>&1 |
    grep -oE '[0-9]+ commits scanned' | head -1 | cut -d' ' -f1)"
  reported_n="$(grep -oE 'no leaks — [0-9]+ commit' <<<"$count_out" | grep -oE '[0-9]+')"

  check "the fixture actually discriminates (rev-list ≠ gitleaks)" \
    [ "$revlist_n" != "$gitleaks_n" ]
  check "the reported count matches gitleaks' own commits-scanned figure" \
    equals "$gitleaks_n" "$reported_n"
  check "the reported count is NOT git rev-list's" \
    [ "$reported_n" != "$revlist_n" ]

  # ===========================================================================
  echo
  echo "a clean tree passes, with its scope stated:"

  fx3="$(new_fixture clean)"
  clean_out="$(cd "$fx3" && "$GATE" --history 2>&1)"
  clean_rc=$?

  check "--history exits 0 on a clean repo" \
    [ "$clean_rc" -eq 0 ]
  check "--history states a clean verdict" \
    contains "no leaks" "$clean_out"
  check "a clean scan of a clean tree prints no PARTIAL banner" \
    not_contains "PARTIAL" "$clean_out"

  # ===========================================================================
  echo
  echo "untracked content is disclosed, never silently skipped:"

  printf 'untracked placeholder\n' >"$fx3/stray.txt"
  stray_out="$(cd "$fx3" && "$GATE" --history 2>&1)"

  check "--history names an untracked file it did not scan" \
    contains "stray.txt" "$stray_out"
  check "--history qualifies that run as PARTIAL" \
    contains "PARTIAL" "$stray_out"

fi # HAVE_GITLEAKS

# ===========================================================================
echo
echo "an absent binary reports NOT RUN and never reads as clean:"
#
# PATH is narrowed to the system directories, which carry bash and git but not
# a brew-installed gitleaks, so `command -v gitleaks` fails exactly as it would
# on a machine that never installed it. Note an EMPTY PATH does not test this:
# it also hides `bash` from the shebang's `env`, so the script never starts and
# every assertion here passes on a 127 that has nothing to do with the gate.

# Its own fixture: every fixture above lives inside the HAVE_GITLEAKS block, and
# this section must run on a machine that has no gitleaks at all.
fx_nobin="$(new_fixture nobin)"
empty_bin="$TMP/empty-bin"
mkdir -p "$empty_bin"
nobin_out="$(cd "$fx_nobin" && PATH="$empty_bin:/usr/bin:/bin" "$GATE" --history 2>&1)"
nobin_rc=$?

check "exits 0 when gitleaks is missing (disclosure, not a blocker)" \
  [ "$nobin_rc" -eq 0 ]
check "says NOT RUN" \
  contains "NOT RUN" "$nobin_out"
check "never says clean when nothing was scanned" \
  not_contains "no leaks" "$nobin_out"
check "names the missing binary so the reader can fix it" \
  contains "gitleaks" "$nobin_out"

# ===========================================================================
echo
echo "argument handling:"

badarg_out="$(cd "$fx_nobin" && "$GATE" --bogus 2>&1)"
badarg_rc=$?

check "an unknown mode exits non-zero rather than guessing" \
  [ "$badarg_rc" -ne 0 ]
check "an unknown mode names the modes it accepts" \
  contains "--staged" "$badarg_out"

# ===========================================================================
echo
echo "fixture isolation:"

GUARD_REFS_AFTER="$(git -C "$REPO_ROOT" for-each-ref | wc -l | tr -d ' ')"
GUARD_HEAD_AFTER="$(git -C "$REPO_ROOT" rev-parse HEAD)"

check "the primary checkout's ref count is unchanged" \
  equals "$GUARD_REFS_BEFORE" "$GUARD_REFS_AFTER"
check "the primary checkout's HEAD is unchanged" \
  equals "$GUARD_HEAD_BEFORE" "$GUARD_HEAD_AFTER"

# ===========================================================================
echo
if [ "$fail" -eq 0 ]; then
  printf '  ✓ all %d assertions pass\n' "$pass"
  exit 0
fi
printf '  ✗ %d of %d assertions failed\n' "$fail" "$((pass + fail))"
exit 1
