#!/usr/bin/env bash
#
# test-install.sh — exercise bin/install.sh end to end against throwaway
# directories. install.sh derives its repo root from its own location, so each
# test builds a tiny fake repo (with fixture items + a copy of install.sh) and
# installs it into a temp --home. Nothing touches your real ~/.claude.
#
# Usage: bin/test-install.sh
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_SRC="$REPO_ROOT/bin/install.sh"

pass=0 fail=0
check() {  # check "description" command...
  local desc="$1"; shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"; pass=$((pass+1))
  else
    printf '  ✗ %s\n' "$desc"; fail=$((fail+1))
  fi
}

# --- predicates used by check ---------------------------------------------
links_to() { [ "$(readlink "$2" 2>/dev/null)" = "$1" ]; }   # links_to TARGET PATH
is_real_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
file_is() { [ "$(cat "$2" 2>/dev/null)" = "$1" ]; }          # file_is CONTENT PATH
contains() { grep -q -- "$1" <<<"$2"; }                      # contains NEEDLE HAYSTACK
not_exists() { [ ! -e "$1" ] && [ ! -L "$1" ]; }             # gone, even as broken link

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# build_repo DIR — a minimal fake claude-kit with one of each item type.
build_repo() {
  local r="$1"
  mkdir -p "$r/bin" "$r/skills/demo" "$r/agents" "$r/commands"
  cp "$INSTALL_SRC" "$r/bin/install.sh"
  printf -- '---\nname: demo\ndescription: demo\n---\n' > "$r/skills/demo/SKILL.md"
  printf -- '---\nname: demo\ndescription: d\n---\nbody\n'      > "$r/agents/demo.md"
  printf -- '---\ndescription: d\n---\nbody\n'                  > "$r/commands/demo.md"
  printf -- '# CLAUDE\n'                                        > "$r/CLAUDE.md"
}

# ===========================================================================
echo "fresh install:"
REPO="$TMP/repo"; HOME_DIR="$TMP/home"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null

check "skill linked"   links_to "$REPO/skills/demo"   "$HOME_DIR/skills/demo"
check "agent linked"   links_to "$REPO/agents/demo.md"   "$HOME_DIR/agents/demo.md"
check "command linked" links_to "$REPO/commands/demo.md" "$HOME_DIR/commands/demo.md"
check "CLAUDE.md linked" links_to "$REPO/CLAUDE.md"   "$HOME_DIR/CLAUDE.md"

echo "idempotent re-run:"
out="$("$REPO/bin/install.sh" --home "$HOME_DIR" 2>&1)"
check "nothing relinked"   contains "0 linked" "$out"
check "reports all current" contains "4 already current" "$out"

# ===========================================================================
echo "conflict safety (foreign items left untouched):"
REPO="$TMP/repo2"; HOME_DIR="$TMP/home2"
build_repo "$REPO"
mkdir -p "$HOME_DIR/commands" "$HOME_DIR/agents"
printf 'do not touch\n' > "$HOME_DIR/commands/demo.md"            # foreign real file
ln -s /etc/hostname "$HOME_DIR/agents/demo.md"                   # foreign symlink
out="$("$REPO/bin/install.sh" --home "$HOME_DIR" 2>&1)"

check "reports conflicts"        contains "CONFLICT" "$out"
check "foreign file untouched"   is_real_file "$HOME_DIR/commands/demo.md"
check "foreign file content kept" file_is "do not touch" "$HOME_DIR/commands/demo.md"
check "foreign symlink untouched" links_to "/etc/hostname" "$HOME_DIR/agents/demo.md"

# ===========================================================================
echo "prune (only broken links into the repo):"
REPO="$TMP/repo3"; HOME_DIR="$TMP/home3"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
rm -rf "$REPO/skills/demo"                                       # break the skill link

# Without --prune the broken link must remain.
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
check "broken link kept without --prune" test -L "$HOME_DIR/skills/demo"

# With --prune it is removed.
out="$("$REPO/bin/install.sh" --home "$HOME_DIR" --prune 2>&1)"
check "reports a prune"        contains "pruned" "$out"
check "broken link removed"    not_exists "$HOME_DIR/skills/demo"

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
