#!/usr/bin/env bash
#
# check-private-info.sh — scan committed/staged content for personal info that
# must never land in a repo: private-relay emails, local home paths, vault
# paths, pasted chat transcripts, private scratch files, and your own denylist
# terms. Offline, plain grep, deliberately boring — read it, edit it.
#
# This catches PERSONAL info (things that identify you); secret material
# (keys, tokens) is covered by detect-private-key and Gitleaks (.gitleaks.toml).
# See docs/privacy-boundaries.md for the full model.
#
# Usage:
#   bin/check-private-info.sh              # scan all tracked files
#   bin/check-private-info.sh FILE...      # scan specific files (pre-commit)
#   bin/check-private-info.sh --self-test  # prove the patterns catch fixtures
#
# Personal denylist: one term per line (case-insensitive fixed strings; '#'
# comments) in ~/.claude-kit/private-denylist.txt, or point CLAUDE_KIT_DENYLIST
# at another file. The denylist itself is personal — never commit it.
#
# False positives: append 'private-ok' to the specific line to vouch for it,
# or add a path to SKIP_FILES below for files that must discuss these
# patterns (this script, the Gitleaks config).
#
set -uo pipefail # not -e: aggregate every finding, then fail once

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

DENYLIST="${CLAUDE_KIT_DENYLIST:-$HOME/.claude-kit/private-denylist.txt}"

# Files allowed to contain the patterns below, because documenting/encoding
# them is their job. Keep this list short and literal.
SKIP_FILES=(
  "bin/check-private-info.sh"
  ".gitleaks.toml"
)

# label<TAB>extended-regex — the content patterns. Edit freely.
PATTERNS="apple-private-relay	[A-Za-z0-9._%+-]+@privaterelay\.appleid\.com
local-home-path	/Users/[A-Za-z][A-Za-z0-9._-]*
obsidian-vault-path	iCloud~md~obsidian|Mobile Documents/[^ ]*[Oo]bsidian
chat-transcript	^(Human|Assistant|USER|ASSISTANT): |^You said:|^(ChatGPT|Claude) said:"

# Tracked paths that should never be committed at all (the .gitignore patterns,
# enforced against force-adds). .env.example is the one allowed exception.
PRIVATE_PATH_RE='(^|/)(\.claude-(private|local|session|scratch)|\.superpowers|notes-private|session-notes|personal-notes)(/|$)|\.private\.md$|\.local\.md$|(^|/)\.scratch\.md$|(^|/)\.env(\.[^/]*)?$'

fail=0
finding() {
  printf '  ✗ %s\n' "$1"
  fail=1
}
ok() { printf '  ✓ %s\n' "$1"; }

is_skipped() {
  local f="$1" s
  for s in "${SKIP_FILES[@]}"; do
    [ "$f" = "$s" ] && return 0
  done
  return 1
}

# scan_file FILE — run every content pattern (and the denylist) over FILE.
# Lines carrying a 'private-ok' marker are vouched-for and skipped.
scan_file() {
  local f="$1" label re hits
  [ -f "$f" ] || return 0
  is_skipped "$f" && return 0
  while IFS=$'\t' read -r label re; do
    [ -n "$label" ] || continue
    hits="$(grep -InE "$re" "$f" 2>/dev/null | grep -v 'private-ok' || true)"
    if [ -n "$hits" ]; then
      while IFS= read -r line; do
        finding "$f:$line [$label]"
      done <<<"$hits"
    fi
  done <<<"$PATTERNS"
  if [ -f "$DENYLIST" ]; then
    local term
    while IFS= read -r term; do
      case "$term" in '' | \#*) continue ;; esac
      hits="$(grep -InF "$term" "$f" 2>/dev/null | grep -v 'private-ok' || true)"
      if [ -n "$hits" ]; then
        while IFS= read -r line; do
          finding "$f:$line [denylist]"
        done <<<"$hits"
      fi
    done <"$DENYLIST"
  fi
}

# scan_verdict FILE — echo the fail flag scan_file would set, in isolation.
# The subshell keeps the fixture verdicts away from the real scan's fail flag.
# shellcheck disable=SC2030,SC2031
scan_verdict() {
  (
    fail=0
    scan_file "$1" >/dev/null
    echo "$fail"
  )
}

self_test() {
  local t pass=0 failed=0 f
  t="$(mktemp -d)"
  # each fixture must be FLAGGED
  printf 'contact me: abc.123@privaterelay.appleid.com\n' >"$t/relay.md"
  printf 'clone into /Users/jane/Developer/proj\n' >"$t/homepath.md"
  printf 'vault: ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/v\n' >"$t/vault.md"
  printf 'Human: please fix this\nAssistant: sure\n' >"$t/transcript.md"
  printf 'my secret term: xyzzy-internal\n' >"$t/denylist.md"
  # these must PASS
  printf 'normal doc, mentions ~/.claude and docs/foo.md\n' >"$t/clean.md"
  printf 'example: /Users/jane/x is bad  <- private-ok\n' >"$t/vouched.md"
  printf 'xyzzy-internal\n' >"$t/deny.txt"

  # DENYLIST=/dev/null keeps your real denylist out of the fixtures' verdicts.
  for f in relay homepath vault transcript; do
    if [ "$(DENYLIST=/dev/null scan_verdict "$t/$f.md")" = 1 ]; then
      pass=$((pass + 1))
    else
      printf '  ✗ self-test: %s.md NOT flagged\n' "$f"
      failed=1
    fi
  done
  if [ "$(DENYLIST="$t/deny.txt" scan_verdict "$t/denylist.md")" = 1 ]; then
    pass=$((pass + 1))
  else
    printf '  ✗ self-test: denylist.md NOT flagged\n'
    failed=1
  fi
  for f in clean vouched; do
    if [ "$(DENYLIST=/dev/null scan_verdict "$t/$f.md")" = 0 ]; then
      pass=$((pass + 1))
    else
      printf '  ✗ self-test: %s.md wrongly flagged\n' "$f"
      failed=1
    fi
  done
  # a private-by-path filename must be refused even as an explicit argument
  if "$0" "$t/session-notes/leak.md" >/dev/null 2>&1; then
    printf '  ✗ self-test: private path session-notes/ NOT flagged\n'
    failed=1
  else
    pass=$((pass + 1))
  fi
  rm -rf "$t"
  printf '  self-test: %d/8 fixtures behaved\n' "$pass"
  return "$failed"
}

if [ "${1:-}" = "--self-test" ]; then
  echo "private-info self-test:"
  if self_test; then
    ok "scanner catches all fixtures, passes clean files"
    exit 0
  else
    echo "private-info self-test FAILED."
    exit 1
  fi
fi

echo "private-info scan:"

# --- 1. no private-by-path files are tracked/staged ------------------------
if [ $# -gt 0 ]; then
  path_hits="$(printf '%s\n' "$@" | grep -E "$PRIVATE_PATH_RE" | grep -v '\.env\.example$' || true)"
else
  path_hits="$(git ls-files | grep -E "$PRIVATE_PATH_RE" | grep -v '\.env\.example$' || true)"
fi
if [ -n "$path_hits" ]; then
  while IFS= read -r p; do
    finding "$p [private file committed — belongs outside the repo or in .gitignore]"
  done <<<"$path_hits"
fi

# --- 2. content patterns + denylist ----------------------------------------
if [ $# -gt 0 ]; then
  for f in "$@"; do scan_file "$f"; done
else
  while IFS= read -r f; do scan_file "$f"; done < <(git ls-files)
fi

if [ ! -f "$DENYLIST" ]; then
  echo "  - no personal denylist at $DENYLIST (optional; one term per line)"
fi

echo
# The self-test's subshell writes to its own copy of fail on purpose (SC2031);
# by this point only the real scan above has touched this one.
# shellcheck disable=SC2031
if [ "$fail" -eq 0 ]; then
  ok "no private info found"
else
  echo "Private info found — fix, or mark a false positive with 'private-ok'."
fi
# shellcheck disable=SC2031
exit "$fail"
