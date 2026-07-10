#!/usr/bin/env bash
#
# test-doctor.sh — exercise bin/doctor.sh end to end against throwaway
# directories. doctor.sh derives its repo root from its own location, so each
# test builds a tiny fake repo (with fixture items + a copy of doctor.sh and
# install.sh) and runs it against temp provider homes. Nothing touches your
# real ~/.claude, ~/.bindle, or any explicit Codex target.
#
# Usage: bin/test-doctor.sh
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR_SRC="$REPO_ROOT/bin/doctor.sh"
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

contains() { grep -qF -- "$1" <<<"$2"; }       # contains NEEDLE HAYSTACK
not_contains() { ! grep -qF -- "$1" <<<"$2"; } # not_contains NEEDLE HAYSTACK
exit_is() { [ "$1" -eq "$2" ]; }               # exit_is ACTUAL EXPECTED

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# build_repo DIR — a minimal fake Bindle repo with one of each item type.
build_repo() {
  local r="$1"
  mkdir -p "$r/bin" "$r/skills/demo" "$r/agents" "$r/commands" "$r/global"
  cp "$DOCTOR_SRC" "$r/bin/doctor.sh"
  cp "$INSTALL_SRC" "$r/bin/install.sh"
  chmod +x "$r/bin/doctor.sh" "$r/bin/install.sh"
  printf -- '---\nname: demo\ndescription: demo\n---\n' >"$r/skills/demo/SKILL.md"
  printf -- '---\nname: demo\ndescription: d\n---\nbody\n' >"$r/agents/demo.md"
  printf -- '---\ndescription: d\n---\nbody\n' >"$r/commands/demo.md"
  printf -- '# CLAUDE\n' >"$r/global/CLAUDE.md"
  printf -- '# AGENTS\n' >"$r/global/AGENTS.md"
  printf -- '0.1.0\n' >"$r/VERSION"
}

# snapshot DIR — a read-only fingerprint of everything under DIR: path +
# kind, symlink target (not followed) or file checksum. Used to prove
# doctor.sh never writes to the home it inspects.
snapshot() {
  local d="$1" p
  [ -e "$d" ] || {
    echo "MISSING $d"
    return 0
  }
  find "$d" | sort | while IFS= read -r p; do
    if [ -L "$p" ]; then
      printf 'L %s -> %s\n' "$p" "$(readlink "$p")"
    elif [ -f "$p" ]; then
      printf 'F %s %s\n' "$p" "$(shasum -a 256 "$p" | awk '{print $1}')"
    elif [ -d "$p" ]; then
      printf 'D %s\n' "$p"
    fi
  done
}

# ===========================================================================
echo "1. healthy after fixture install:"
REPO="$TMP/repo1"
HOME_DIR="$TMP/home1"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
status=$?

check "exits zero" exit_is "$status" 0
check "reports skill current" contains "skills/demo — current" "$out"
check "reports agent current" contains "agents/demo.md — current" "$out"
check "reports command current" contains "commands/demo.md — current" "$out"
check "reports global CLAUDE.md current" contains "global/CLAUDE.md — current" "$out"
check "summary shows 4 current" contains "4 current" "$out"

# ===========================================================================
echo "2. fresh empty home:"
REPO="$TMP/repo2"
HOME_DIR="$TMP/home2"
build_repo "$REPO"
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
status=$?

check "exits nonzero" test "$status" -ne 0
check "reports skill missing" contains "skills/demo — missing" "$out"
check "missing action points at install.sh" contains "run: bin/install.sh" "$out"

# ===========================================================================
echo "3. real file at a dest (conflict):"
REPO="$TMP/repo3"
HOME_DIR="$TMP/home3"
build_repo "$REPO"
mkdir -p "$HOME_DIR/commands"
printf 'do not touch\n' >"$HOME_DIR/commands/demo.md"
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
status=$?

check "reports conflict" contains "commands/demo.md — conflict" "$out"
check "exits nonzero" test "$status" -ne 0
check "real file left untouched" test -f "$HOME_DIR/commands/demo.md"

# ===========================================================================
echo "4. foreign symlink (conflict):"
REPO="$TMP/repo4"
HOME_DIR="$TMP/home4"
build_repo "$REPO"
FOREIGN_TARGET="$TMP/foreign-target-4"
printf 'foreign\n' >"$FOREIGN_TARGET"
mkdir -p "$HOME_DIR/agents"
ln -s "$FOREIGN_TARGET" "$HOME_DIR/agents/demo.md"
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"

check "reports conflict" contains "agents/demo.md — conflict" "$out"
check "foreign symlink left untouched" test "$(readlink "$HOME_DIR/agents/demo.md")" = "$FOREIGN_TARGET"

# ===========================================================================
echo "5. broken owned link (deleted fixture item, prunable via sweep):"
REPO="$TMP/repo5"
HOME_DIR="$TMP/home5"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
rm -rf "$REPO/skills/demo" # delete the source item entirely
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"

check "reports broken" contains "skills/demo — broken" "$out"
check "suggests prune" contains "--prune" "$out"
check "broken link left untouched" test -L "$HOME_DIR/skills/demo"

# ===========================================================================
echo "6. stale owned link (points at a different existing item in-repo):"
REPO="$TMP/repo6"
HOME_DIR="$TMP/home6"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
rm "$HOME_DIR/agents/demo.md"
ln -s "$REPO/skills/demo" "$HOME_DIR/agents/demo.md" # existing, but wrong, in-repo target
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"

check "reports stale" contains "agents/demo.md — stale" "$out"
check "suggests install.sh relink" contains "bin/install.sh (relinks owned items)" "$out"

# ===========================================================================
echo "7. earlier-checkout (deleted prior checkout, surviving fixture elsewhere):"
REPO_A="$TMP/checkout-a/repo"
HOME_DIR="$TMP/home7"
build_repo "$REPO_A"
"$REPO_A/bin/install.sh" --home "$HOME_DIR" >/dev/null
rm -rf "$TMP/checkout-a" # the old checkout is gone; links now dangle

REPO_B="$TMP/checkout-b/repo"
build_repo "$REPO_B"
out="$("$REPO_B/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
status=$?

check "reports tentative earlier-checkout wording" contains "possibly an earlier Bindle checkout at" "$out"
check "names the old checkout path" contains "$TMP/checkout-a/repo" "$out"
check "exits nonzero" test "$status" -ne 0

# ===========================================================================
echo "8. notes home resolution:"
REPO="$TMP/repo8"
HOME_DIR="$TMP/home8"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null # healthy install: isolates notes-home findings

echo "  8a. BINDLE_NOTES_DIR set to an existing dir:"
NOTES_OK="$TMP/notes-ok"
mkdir -p "$NOTES_OK/projects/demo-project"
out="$(env -u CLAUDE_KIT_NOTES_DIR BINDLE_NOTES_DIR="$NOTES_OK" "$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
status=$?
check "resolved from BINDLE_NOTES_DIR" contains "via BINDLE_NOTES_DIR)" "$out"
check "reports the dir" contains "$NOTES_OK" "$out"
check "exits zero (no findings)" exit_is "$status" 0

echo "  8b. BINDLE_NOTES_DIR set but missing:"
NOTES_MISSING="$TMP/notes-missing-does-not-exist"
out="$(env -u CLAUDE_KIT_NOTES_DIR BINDLE_NOTES_DIR="$NOTES_MISSING" "$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
status=$?
check "reports notes-home as a finding" contains "notes-home — missing" "$out"
check "exits nonzero" test "$status" -ne 0

echo "  8c. CLAUDE_KIT_NOTES_DIR triggers deprecation note:"
NOTES_LEGACY="$TMP/notes-legacy"
mkdir -p "$NOTES_LEGACY"
out="$(env -u BINDLE_NOTES_DIR CLAUDE_KIT_NOTES_DIR="$NOTES_LEGACY" "$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
check "resolved from CLAUDE_KIT_NOTES_DIR" contains "via CLAUDE_KIT_NOTES_DIR (deprecated))" "$out"
check "notes deprecation note present" contains "CLAUDE_KIT_NOTES_DIR is deprecated" "$out"

# ===========================================================================
echo "9. codex section:"
REPO="$TMP/repo9"
HOME_DIR="$TMP/home9"
CODEX_HOME="$TMP/codex9"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" >/dev/null

out_with="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" --codex-home "$CODEX_HOME" 2>&1)"
check "codex section present" contains "codex home (" "$out_with"
check "AGENTS.md reported current" contains "global/AGENTS.md — current" "$out_with"

out_without="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
check "no codex section without the flag" not_contains "codex home (" "$out_without"

# ===========================================================================
echo "10. read-only guarantee:"
REPO="$TMP/repo10"
HOME_DIR="$TMP/home10"
CODEX_HOME="$TMP/codex10"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" >/dev/null
# add a mix of conflict/stale/broken items so every code path runs.
mkdir -p "$HOME_DIR/commands"
printf 'do not touch\n' >"$HOME_DIR/commands/other.md"
ln -s "$TMP/foreign-target-10" "$HOME_DIR/agents/other.md" 2>/dev/null || true
printf 'foreign\n' >"$TMP/foreign-target-10"
rm "$HOME_DIR/skills/demo" 2>/dev/null
ln -s "$REPO/agents/demo.md" "$HOME_DIR/skills/demo"

before="$(snapshot "$HOME_DIR")"
before_codex="$(snapshot "$CODEX_HOME")"
"$REPO/bin/doctor.sh" --home "$HOME_DIR" --codex-home "$CODEX_HOME" >/dev/null 2>&1
env -u BINDLE_NOTES_DIR BINDLE_NOTES_DIR="$TMP/does-not-exist-ro" "$REPO/bin/doctor.sh" --home "$HOME_DIR" >/dev/null 2>&1
after="$(snapshot "$HOME_DIR")"
after_codex="$(snapshot "$CODEX_HOME")"

check "claude home byte-identical before/after" test "$before" = "$after"
check "codex home byte-identical before/after" test "$before_codex" = "$after_codex"

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
