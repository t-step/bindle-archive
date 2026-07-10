#!/usr/bin/env bash
#
# test-install.sh — exercise bin/install.sh end to end against throwaway
# directories. install.sh derives its repo root from its own location, so each
# test builds a tiny fake repo (with fixture items + a copy of install.sh) and
# installs it into temp provider homes. Nothing touches your real ~/.claude or
# any explicit Codex target.
#
# Usage: bin/test-install.sh
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_SRC="$REPO_ROOT/bin/install.sh"

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

# --- predicates used by check ---------------------------------------------
links_to() { [ "$(readlink "$2" 2>/dev/null)" = "$1" ]; } # links_to TARGET PATH
is_real_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
file_is() { [ "$(cat "$2" 2>/dev/null)" = "$1" ]; } # file_is CONTENT PATH
contains() { grep -q -- "$1" <<<"$2"; }             # contains NEEDLE HAYSTACK
not_contains() { ! grep -q -- "$1" <<<"$2"; }       # not_contains NEEDLE HAYSTACK
not_exists() { [ ! -e "$1" ] && [ ! -L "$1" ]; }    # gone, even as broken link

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# build_repo DIR — a minimal fake Bindle repo with one of each item type.
build_repo() {
  local r="$1"
  mkdir -p "$r/bin" "$r/skills/demo" "$r/agents" "$r/commands" "$r/global"
  cp "$INSTALL_SRC" "$r/bin/install.sh"
  printf -- '---\nname: demo\ndescription: demo\n---\n' >"$r/skills/demo/SKILL.md"
  printf -- '---\nname: demo\ndescription: d\n---\nbody\n' >"$r/agents/demo.md"
  printf -- '---\ndescription: d\n---\nbody\n' >"$r/commands/demo.md"
  printf -- '# CLAUDE\n' >"$r/global/CLAUDE.md"
  printf -- '# AGENTS\n' >"$r/global/AGENTS.md"
}

# ===========================================================================
echo "fresh install:"
REPO="$TMP/repo"
HOME_DIR="$TMP/home"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
status=$?

check "clean install exits zero" test "$status" -eq 0
check "skill linked" links_to "$REPO/skills/demo" "$HOME_DIR/skills/demo"
check "agent linked" links_to "$REPO/agents/demo.md" "$HOME_DIR/agents/demo.md"
check "command linked" links_to "$REPO/commands/demo.md" "$HOME_DIR/commands/demo.md"
check "CLAUDE.md linked" links_to "$REPO/global/CLAUDE.md" "$HOME_DIR/CLAUDE.md"

echo "idempotent re-run:"
out="$("$REPO/bin/install.sh" --home "$HOME_DIR" 2>&1)"
check "nothing relinked" contains "0 linked" "$out"
check "reports all current" contains "4 already current" "$out"

# ===========================================================================
echo "conflict safety (foreign items left untouched):"
REPO="$TMP/repo2"
HOME_DIR="$TMP/home2"
build_repo "$REPO"
mkdir -p "$HOME_DIR/commands" "$HOME_DIR/agents"
printf 'do not touch\n' >"$HOME_DIR/commands/demo.md" # foreign real file
ln -s /etc/hostname "$HOME_DIR/agents/demo.md"        # foreign symlink
out="$("$REPO/bin/install.sh" --home "$HOME_DIR" 2>&1)"

check "reports conflicts" contains "CONFLICT" "$out"
check "foreign file untouched" is_real_file "$HOME_DIR/commands/demo.md"
check "foreign file content kept" file_is "do not touch" "$HOME_DIR/commands/demo.md"
check "foreign symlink untouched" links_to "/etc/hostname" "$HOME_DIR/agents/demo.md"

"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null 2>&1
status=$?
check "conflict causes nonzero exit" test "$status" -ne 0

echo "conflict safety with --allow-conflicts:"
out="$("$REPO/bin/install.sh" --home "$HOME_DIR" --allow-conflicts 2>&1)"
status=$?
check "allow-conflicts still reports conflicts" contains "CONFLICT" "$out"
check "allow-conflicts exits zero" test "$status" -eq 0
check "allow-conflicts leaves foreign file untouched" is_real_file "$HOME_DIR/commands/demo.md"

# ===========================================================================
echo "codex install with explicit target:"
REPO="$TMP/repo-codex"
CODEX_HOME="$TMP/codex-home"
build_repo "$REPO"
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" >/dev/null

check "AGENTS.md linked" links_to "$REPO/global/AGENTS.md" "$CODEX_HOME/AGENTS.md"
check "Claude-only skills not installed for Codex" not_exists "$CODEX_HOME/skills/demo"

echo "codex install requires explicit target:"
REPO="$TMP/repo-codex-missing-home"
build_repo "$REPO"
out="$("$REPO/bin/install.sh" --provider codex 2>&1)"
status=$?
check "missing --codex-home fails" test "$status" -ne 0
check "missing --codex-home explains explicit target" contains "--codex-home" "$out"

echo "all providers install:"
REPO="$TMP/repo-all"
CLAUDE_HOME="$TMP/all-claude"
CODEX_HOME="$TMP/all-codex"
build_repo "$REPO"
"$REPO/bin/install.sh" --provider all --home "$CLAUDE_HOME" --codex-home "$CODEX_HOME" >/dev/null

check "all links Claude skill" links_to "$REPO/skills/demo" "$CLAUDE_HOME/skills/demo"
check "all links Claude global" links_to "$REPO/global/CLAUDE.md" "$CLAUDE_HOME/CLAUDE.md"
check "all links Codex global" links_to "$REPO/global/AGENTS.md" "$CODEX_HOME/AGENTS.md"

echo "codex conflict safety:"
REPO="$TMP/repo-codex-conflict"
CODEX_HOME="$TMP/codex-conflict"
build_repo "$REPO"
mkdir -p "$CODEX_HOME"
printf 'do not touch\n' >"$CODEX_HOME/AGENTS.md"
out="$("$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" 2>&1)"
status=$?

check "codex reports conflicts" contains "CONFLICT" "$out"
check "codex conflict causes nonzero exit" test "$status" -ne 0
check "codex foreign file untouched" is_real_file "$CODEX_HOME/AGENTS.md"
check "codex foreign file content kept" file_is "do not touch" "$CODEX_HOME/AGENTS.md"

# ===========================================================================
echo "prune (only broken links into the repo):"
REPO="$TMP/repo3"
HOME_DIR="$TMP/home3"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
rm -rf "$REPO/skills/demo" # break the skill link

# Without --prune the broken link must remain.
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
check "broken link kept without --prune" test -L "$HOME_DIR/skills/demo"

# With --prune it is removed.
out="$("$REPO/bin/install.sh" --home "$HOME_DIR" --prune 2>&1)"
check "reports a prune" contains "pruned" "$out"
check "broken link removed" not_exists "$HOME_DIR/skills/demo"

echo "codex prune (only broken links into the repo):"
REPO="$TMP/repo-codex-prune"
CODEX_HOME="$TMP/codex-prune"
build_repo "$REPO"
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" >/dev/null
rm "$REPO/global/AGENTS.md"

"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" >/dev/null
check "codex broken link kept without --prune" test -L "$CODEX_HOME/AGENTS.md"

out="$("$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" --prune 2>&1)"
check "codex reports a prune" contains "pruned" "$out"
check "codex broken link removed" not_exists "$CODEX_HOME/AGENTS.md"

# ===========================================================================
echo "moved-repo adoption (--adopt, confirmed):"
REPO_A="$TMP/adopt1-a/repo"
HOME_DIR="$TMP/adopt1-home"
build_repo "$REPO_A"
"$REPO_A/bin/install.sh" --home "$HOME_DIR" >/dev/null
rm -rf "$TMP/adopt1-a" # the old checkout is gone; owned links now dangle

REPO_B="$TMP/adopt1-b/repo"
build_repo "$REPO_B"
out="$(printf 'y\n' | "$REPO_B/bin/install.sh" --home "$HOME_DIR" --adopt 2>&1)"
status=$?

check "adopt (confirmed) exits zero" test "$status" -eq 0
check "adopt (confirmed) shows a preview" contains "Adoption candidates" "$out"
check "adopt (confirmed) reports adopted count" contains "adopted 4 link(s) from an earlier checkout" "$out"
check "skill relinked into surviving checkout" links_to "$REPO_B/skills/demo" "$HOME_DIR/skills/demo"
check "agent relinked into surviving checkout" links_to "$REPO_B/agents/demo.md" "$HOME_DIR/agents/demo.md"
check "command relinked into surviving checkout" links_to "$REPO_B/commands/demo.md" "$HOME_DIR/commands/demo.md"
check "CLAUDE.md relinked into surviving checkout" links_to "$REPO_B/global/CLAUDE.md" "$HOME_DIR/CLAUDE.md"

echo "moved-repo adoption re-run is idempotent:"
out2="$("$REPO_B/bin/install.sh" --home "$HOME_DIR" --adopt 2>&1)"
status2=$?
check "idempotent re-run exits zero" test "$status2" -eq 0
check "idempotent re-run: nothing relinked" contains "0 linked" "$out2"
check "idempotent re-run: no adoption preview" not_contains "Adoption candidates" "$out2"

# ===========================================================================
echo "moved-repo adoption declined ('n'):"
REPO_A2="$TMP/adopt2-a/repo"
HOME_DIR2="$TMP/adopt2-home"
build_repo "$REPO_A2"
"$REPO_A2/bin/install.sh" --home "$HOME_DIR2" >/dev/null
OLD_SKILL_TARGET="$REPO_A2/skills/demo"
rm -rf "$TMP/adopt2-a"

REPO_B2="$TMP/adopt2-b/repo"
build_repo "$REPO_B2"
out="$(printf 'n\n' | "$REPO_B2/bin/install.sh" --home "$HOME_DIR2" --adopt 2>&1)"
status=$?

check "declined adopt shows a preview" contains "Adoption candidates" "$out"
check "declined adopt reports CONFLICT" contains "CONFLICT" "$out"
check "declined adopt link left untouched" links_to "$OLD_SKILL_TARGET" "$HOME_DIR2/skills/demo"
check "declined adopt exits nonzero" test "$status" -ne 0

out_allow="$(printf 'n\n' | "$REPO_B2/bin/install.sh" --home "$HOME_DIR2" --adopt --allow-conflicts 2>&1)"
status_allow=$?
check "declined adopt + allow-conflicts still reports CONFLICT" contains "CONFLICT" "$out_allow"
check "declined adopt + allow-conflicts exits zero" test "$status_allow" -eq 0
check "declined adopt + allow-conflicts leaves link untouched" links_to "$OLD_SKILL_TARGET" "$HOME_DIR2/skills/demo"

echo "moved-repo adoption declined (empty stdin/EOF):"
REPO_A2b="$TMP/adopt2b-a/repo"
HOME_DIR2b="$TMP/adopt2b-home"
build_repo "$REPO_A2b"
"$REPO_A2b/bin/install.sh" --home "$HOME_DIR2b" >/dev/null
OLD_SKILL_TARGET_B="$REPO_A2b/skills/demo"
rm -rf "$TMP/adopt2b-a"

REPO_B2b="$TMP/adopt2b-b/repo"
build_repo "$REPO_B2b"
out="$("$REPO_B2b/bin/install.sh" --home "$HOME_DIR2b" --adopt </dev/null 2>&1)"
status=$?

check "EOF stdin declines adoption" contains "CONFLICT" "$out"
check "EOF stdin link left untouched" links_to "$OLD_SKILL_TARGET_B" "$HOME_DIR2b/skills/demo"
check "EOF stdin exits nonzero" test "$status" -ne 0

# ===========================================================================
echo "moved-repo adoption never adopts non-candidates (--adopt + 'y'):"
REPO=$TMP/adopt3-repo
HOME_DIR=$TMP/adopt3-home
build_repo "$REPO"
mkdir -p "$HOME_DIR/agents" "$HOME_DIR/commands"

# (a) broken foreign link whose target does NOT end with the expected suffix.
ln -s "$TMP/adopt3-foreign-nomatch" "$HOME_DIR/agents/demo.md"

# (b) LIVE foreign symlink whose target ends with a matching suffix but exists.
mkdir -p "$TMP/adopt3-foreign-live/commands"
printf 'live\n' >"$TMP/adopt3-foreign-live/commands/demo.md"
ln -s "$TMP/adopt3-foreign-live/commands/demo.md" "$HOME_DIR/commands/demo.md"

# (c) a real file at a dest.
printf 'real file\n' >"$HOME_DIR/CLAUDE.md"

out="$(printf 'y\n' | "$REPO/bin/install.sh" --home "$HOME_DIR" --adopt 2>&1)"
status=$?

check "non-candidates: no adoption preview shown" not_contains "Adoption candidates" "$out"
check "non-candidates: reports three conflicts" test "$(grep -c 'CONFLICT' <<<"$out")" -eq 3
check "non-candidates: mismatched-suffix broken link untouched" links_to "$TMP/adopt3-foreign-nomatch" "$HOME_DIR/agents/demo.md"
check "non-candidates: live matching-suffix link untouched" links_to "$TMP/adopt3-foreign-live/commands/demo.md" "$HOME_DIR/commands/demo.md"
check "non-candidates: live foreign content kept" file_is "live" "$TMP/adopt3-foreign-live/commands/demo.md"
check "non-candidates: real file untouched" file_is "real file" "$HOME_DIR/CLAUDE.md"
check "non-candidates: exits nonzero" test "$status" -ne 0

# ===========================================================================
echo "moved-repo regression (without --adopt, unchanged behavior):"
REPO_A4="$TMP/adopt4-a/repo"
HOME_DIR4="$TMP/adopt4-home"
build_repo "$REPO_A4"
"$REPO_A4/bin/install.sh" --home "$HOME_DIR4" >/dev/null
OLD_SKILL_TARGET_4="$REPO_A4/skills/demo"
rm -rf "$TMP/adopt4-a"

REPO_B4="$TMP/adopt4-b/repo"
build_repo "$REPO_B4"
out="$("$REPO_B4/bin/install.sh" --home "$HOME_DIR4" 2>&1)"
status=$?

check "no --adopt: reports CONFLICT" contains "CONFLICT" "$out"
check "no --adopt: no adoption preview" not_contains "Adoption candidates" "$out"
check "no --adopt: link left untouched" links_to "$OLD_SKILL_TARGET_4" "$HOME_DIR4/skills/demo"
check "no --adopt: exits nonzero" test "$status" -ne 0

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
