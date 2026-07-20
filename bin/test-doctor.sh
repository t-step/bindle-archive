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
export HOME="$TMP/home-env"
mkdir -p "$HOME"
export PATH="$HOME/.local/bin:$PATH"

# build_repo DIR — a minimal fake Bindle repo with one of each item type.
build_repo() {
  local r="$1"
  rm -f "$HOME/.local/bin/bindle"
  mkdir -p "$r/bin" "$r/skills/demo" "$r/agents" "$r/commands" "$r/global"
  cp "$DOCTOR_SRC" "$r/bin/doctor.sh"
  cp "$INSTALL_SRC" "$r/bin/install.sh"
  printf '#!/usr/bin/env bash\nprintf "fake bindle\\n"\n' >"$r/bin/bindle"
  chmod +x "$r/bin/doctor.sh" "$r/bin/install.sh" "$r/bin/bindle"
  printf -- '---\nname: demo\ndescription: demo\n---\n' >"$r/skills/demo/SKILL.md"
  printf -- '---\nname: demo\ndescription: d\n---\nbody\n' >"$r/agents/demo.md"
  printf -- '---\ndescription: d\n---\nbody\n' >"$r/commands/demo.md"
  printf -- '# CLAUDE\n' >"$r/global/CLAUDE.md"
  printf -- '# AGENTS\n' >"$r/global/AGENTS.md"
  printf -- '0.1.0\n' >"$r/VERSION"

  mkdir -p "$r/bin/lib"
  cp "$REPO_ROOT/bin/lib/manifest.sh" "$r/bin/lib/manifest.sh"
  cat >"$r/install-manifest.tsv" <<'TSV'
# GENERATED from capabilities.json — do not edit; run 'make manifest'
claude	skill	demo	skills/demo	skills/demo
claude	agent	demo	agents/demo.md	agents/demo.md
claude	command	demo	commands/demo.md	commands/demo.md
claude	global-guidance	claude	global/CLAUDE.md	CLAUDE.md
codex	global-guidance	agents	global/AGENTS.md	AGENTS.md
local	executable	bindle	bin/bindle	bindle
TSV
}

# add_codex_skill DIR NAME — add a Codex-eligible skill to an already-built
# fixture repo, appending both its Claude and Codex manifest rows.
add_codex_skill() {
  local r="$1" name="$2"
  mkdir -p "$r/skills/$name"
  printf -- '---\nname: %s\ndescription: codex-eligible demo\n---\n' "$name" >"$r/skills/$name/SKILL.md"
  {
    printf 'claude\tskill\t%s\tskills/%s\tskills/%s\n' "$name" "$name" "$name"
    printf 'codex\tskill\t%s\tskills/%s\t%s\n' "$name" "$name" "$name"
  } >>"$r/install-manifest.tsv"
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
BIN_DIR="$TMP/bin1"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" --bin-dir "$BIN_DIR" >/dev/null
out="$(PATH="$BIN_DIR:$PATH" "$REPO/bin/doctor.sh" --home "$HOME_DIR" --bin-dir "$BIN_DIR" 2>&1)"
status=$?

check "exits zero" exit_is "$status" 0
check "reports skill current" contains "skills/demo — current" "$out"
check "reports agent current" contains "agents/demo.md — current" "$out"
check "reports command current" contains "commands/demo.md — current" "$out"
check "reports global CLAUDE.md current" contains "global/CLAUDE.md — current" "$out"
check "reports bindle executable current" contains "bin/bindle — current" "$out"
check "summary shows 5 current" contains "5 current" "$out"

echo "1b. bin-dir PATH remediation:"
REPO="$TMP/repo1b"
HOME_DIR="$TMP/home1b"
BIN_DIR="$TMP/not-on-path/bin"
build_repo "$REPO"
"$REPO/bin/install.sh" --home "$HOME_DIR" --bin-dir "$BIN_DIR" >/dev/null
out="$(PATH="/usr/bin:/bin" "$REPO/bin/doctor.sh" --home "$HOME_DIR" --bin-dir "$BIN_DIR" 2>&1)"
status=$?
check "doctor reports bindle path remediation" contains "Add $BIN_DIR to PATH" "$out"
check "PATH remediation is a finding" test "$status" -ne 0

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

# ===========================================================================
echo "11. codex agent-skills section:"
REPO="$TMP/repo11"
HOME_DIR="$TMP/home11"
CODEX_HOME="$TMP/codex11"
AGENTS_SKILLS_HOME="$TMP/agents-skills11"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null

out_with="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" --agents-skills-home "$AGENTS_SKILLS_HOME" 2>&1)"
check "agent-skills section present" contains "codex agent-skills home (" "$out_with"
check "eligible skill reported current" contains "demo-codex — current" "$out_with"

out_without="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
check "no agent-skills section without the flag" not_contains "codex agent-skills home (" "$out_without"

echo "12. codex agent-skills section reports findings:"
REPO="$TMP/repo12"
HOME_DIR="$TMP/home12"
CODEX_HOME="$TMP/codex12"
AGENTS_SKILLS_HOME="$TMP/agents-skills12"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
rm -rf "$REPO/skills/demo-codex" # break the codex skill link

out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" --agents-skills-home "$AGENTS_SKILLS_HOME" 2>&1)"
status=$?
check "broken codex skill link reported" contains "demo-codex — broken" "$out"
check "findings cause nonzero exit" test "$status" -ne 0

echo "13. codex agent-skills read-only guarantee:"
REPO="$TMP/repo13"
HOME_DIR="$TMP/home13"
CODEX_HOME="$TMP/codex13"
AGENTS_SKILLS_HOME="$TMP/agents-skills13"
build_repo "$REPO"
add_codex_skill "$REPO" demo-codex
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null
"$REPO/bin/install.sh" --provider codex --codex-home "$CODEX_HOME" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null
before_agents="$(snapshot "$AGENTS_SKILLS_HOME")"
"$REPO/bin/doctor.sh" --home "$HOME_DIR" --agents-skills-home "$AGENTS_SKILLS_HOME" >/dev/null 2>&1
after_agents="$(snapshot "$AGENTS_SKILLS_HOME")"
check "agent-skills home byte-identical before/after" test "$before_agents" = "$after_agents"

# ===========================================================================
echo "14. hooks section (#264):"
REPO="$TMP/repo14"
HOME_DIR="$TMP/home14"
build_repo "$REPO"
mkdir -p "$REPO/global/hooks"
printf '#!/usr/bin/env python3\nprint("guard")\n' >"$REPO/global/hooks/demo-guard.py"
"$REPO/bin/install.sh" --home "$HOME_DIR" >/dev/null 2>&1

out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
check "hooks section present" contains "claude hooks (" "$out"
check "installed hook reported current" contains "hook: demo-guard.py — current" "$out"

# The failure #264 exists to surface: settings.json names a hook path that no
# longer resolves. Silent before this check; a finding now.
echo "15. hook configured but not reachable (#264):"
cat >"$HOME_DIR/settings.json" <<JSON
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3 $TMP/gone/nested-notes-guard.py"}]}]}}
JSON
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
status=$?
check "unreachable wired hook is reported" contains "configured but NOT reachable" "$out"
check "unreachable wired hook names the fix" contains "re-run bin/install.sh" "$out"
check "unreachable wired hook is a finding" test "$status" -ne 0

# A hook whose wired path resolves is not a finding.
#
# Mutation note: with hooks_section's wiring loop disabled, cases 15 and the
# first assertion of 16 flip to failing, so they are load-bearing. The
# "not flagged" assertion below passes vacuously under that mutation — an
# absence assertion cannot detect a missing check. Kept as a regression guard
# against a future over-eager flag, not counted as failability evidence.
echo "16. hook wired to a resolving path is clean (#264):"
cat >"$HOME_DIR/settings.json" <<JSON
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3 $HOME_DIR/hooks/demo-guard.py"}]}]}}
JSON
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
check "resolving wired hook reported ok" contains "resolves" "$out"
check "resolving wired hook is not flagged" not_contains "configured but NOT reachable" "$out"
check "hook wired via the stable symlink is not drift" not_contains "bypasses" "$out"

# The drift #312 was filed on: settings.json names a path that RESOLVES, but
# into the checkout rather than the $CLAUDE_HOME/hooks symlink. Doctor showed
# this green — indistinguishable from correct wiring — which is why the entry
# sat on the pre-#264 form for two releases after the relocation shipped.
#
# Mutation note: with the checkout-path branch removed, both assertions below
# flip to failing (the line reverts to a plain "resolves" and the run exits 0).
echo "17. hook wired to a checkout-absolute path is drift (#312):"
cat >"$HOME_DIR/settings.json" <<JSON
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3 $REPO/global/hooks/demo-guard.py"}]}]}}
JSON
out="$("$REPO/bin/doctor.sh" --home "$HOME_DIR" 2>&1)"
status=$?
check "checkout-absolute wired hook is reported" contains "bypasses $HOME_DIR/hooks" "$out"
check "checkout-absolute wired hook names the fix" contains "point settings.json at" "$out"
check "checkout-absolute wired hook is a finding" test "$status" -ne 0
check "checkout-absolute drift counted in the summary" contains "1 hook-wiring drift" "$out"

# The state #323 was filed on: a hook that is installed and symlinked but that
# settings.json never names. Every check above passes for it, so before this it
# reported as fully healthy — which is how #287's label-hygiene guard shipped
# and never fired once.
#
# Mutation note: with the unwired loop removed, every "reported" assertion below
# flips to failing. The "not a finding" assertion passes vacuously under that
# mutation; it guards the opt-in contract, not failability.
echo "18. hook installed but never wired (#323):"
REPO18="$TMP/repo18"
HOME18="$TMP/home18"
build_repo "$REPO18"
mkdir -p "$REPO18/global/hooks"
printf '#!/usr/bin/env python3\nprint("guard")\n' >"$REPO18/global/hooks/demo-guard.py"
printf '#!/usr/bin/env python3\nprint("other")\n' >"$REPO18/global/hooks/other-guard.py"
"$REPO18/bin/install.sh" --home "$HOME18" >/dev/null 2>&1
cat >"$HOME18/settings.json" <<JSON
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3 $HOME18/hooks/demo-guard.py"}]}]}}
JSON
out="$("$REPO18/bin/doctor.sh" --home "$HOME18" 2>&1)"
status=$?
check "unwired hook is reported" contains "installed, not wired: other-guard.py" "$out"
check "unwired report names how to wire it" contains "bin/install-claude-hooks.sh status" "$out"
check "the wired hook is NOT listed as unwired" not_contains "installed, not wired: demo-guard.py" "$out"
check "unwired hook is not a finding (wiring is opt-in)" test "$status" -eq 0

echo "19. no settings.json at all — every hook reports unwired (#323):"
HOME19="$TMP/home19"
"$REPO18/bin/install.sh" --home "$HOME19" >/dev/null 2>&1
rm -f "$HOME19/settings.json"
out="$("$REPO18/bin/doctor.sh" --home "$HOME19" 2>&1)"
status=$?
check "absent settings.json is stated" contains "settings.json absent" "$out"
check "absent settings.json points at the installer" contains "bin/install-claude-hooks.sh" "$out"
check "first hook reported unwired" contains "installed, not wired: demo-guard.py" "$out"
check "second hook reported unwired" contains "installed, not wired: other-guard.py" "$out"
check "absent settings.json is not a finding" test "$status" -eq 0

# --- result ----------------------------------------------------------------
echo
echo "tests: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
