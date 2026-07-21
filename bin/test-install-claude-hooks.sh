#!/usr/bin/env bash
#
# test-install-claude-hooks.sh — exercise bin/install-claude-hooks.sh end
# to end against throwaway --home directories. Never touches your real
# ~/.claude/settings.json.
#
# Usage: bin/test-install-claude-hooks.sh
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISH="$REPO_ROOT/bin/install-claude-hooks.sh"

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

contains() { grep -qF -- "$1" <<<"$2"; }
not_contains() { ! grep -qF -- "$1" <<<"$2"; }
exit_is() { [ "$1" -eq "$2" ]; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

run_ish() { # run_ish CLAUDE_HOME -- ARGS...
  local home="$1"
  shift 2 # drop CLAUDE_HOME and the --
  "$ISH" --home "$home" "$@"
}

echo "1. status before install:"
H1="$TMP/h1"
mkdir -p "$H1"
out="$(run_ish "$H1" -- status 2>&1)"
check "reports not wired" contains "not wired" "$out"
check "status lists session-start-context.py" contains "session-start-context.py" "$out"
check "status lists session-end-breadcrumb.py" contains "session-end-breadcrumb.py" "$out"
check "status lists nested-notes-guard.py" contains "nested-notes-guard.py" "$out"
check "status lists label-hygiene-guard.py" contains "label-hygiene-guard.py" "$out"
check "status lists codegraph-chaining-guard.py" contains "codegraph-chaining-guard.py" "$out"
check "an unwired guard names the command that would wire it" contains "install --guard label-hygiene" "$out"

echo
echo "2. install — preview by default (no TTY, no --apply):"
before_exists=false
[ -f "$H1/settings.json" ] && before_exists=true
out="$(run_ish "$H1" -- install 2>&1)"
status=$?
check "preview exits 0" exit_is "$status" 0
check "preview shows SessionStart" contains "SessionStart" "$out"
check "preview shows SessionEnd" contains "SessionEnd" "$out"
check "preview says nothing was written" contains "no changes written" "$out"
check "preview mentions --apply" contains -- "--apply" "$out"
check "settings.json still absent after preview" [ "$before_exists" = false ] && [ ! -f "$H1/settings.json" ]

echo
echo "3. install --apply — surgical write:"
out="$(run_ish "$H1" -- install --apply 2>&1)"
status=$?
check "apply exits 0" exit_is "$status" 0
check "settings.json created" [ -f "$H1/settings.json" ]
check "output confirms installed" contains "installed" "$out"
content="$(cat "$H1/settings.json")"
check "SessionStart wired to session-start-context.py" contains "session-start-context.py" "$content"
check "SessionEnd wired to session-end-breadcrumb.py" contains "session-end-breadcrumb.py" "$content"
check "SessionStart matcher is startup|resume" contains "startup|resume" "$content"
check "settings.json is valid JSON" python3 -c "import json; json.load(open('$H1/settings.json'))"
# The #323 invariant: a bare install must not start intercepting tool calls.
check "bare install did NOT wire the nested-notes guard" not_contains "nested-notes-guard.py" "$content"
check "bare install did NOT wire the label-hygiene guard" not_contains "label-hygiene-guard.py" "$content"
check "bare install did NOT wire the codegraph guard" not_contains "codegraph-chaining-guard.py" "$content"
check "bare install wrote no PreToolUse block at all" not_contains "PreToolUse" "$content"

echo
echo "4. status after install:"
out="$(tr -s ' ' <<<"$(run_ish "$H1" -- status 2>&1)")"
check "session hook reports wired" contains "session-start-context.py SessionStart wired" "$out"
check "an installed-but-unwired guard is still visible" contains "codegraph-chaining-guard.py PreToolUse not wired" "$out"

echo
echo "5. install --apply again is idempotent:"
before="$(cat "$H1/settings.json")"
out="$(run_ish "$H1" -- install --apply 2>&1)"
check "second install reports nothing to do" contains "nothing to do" "$out"
after="$(cat "$H1/settings.json")"
check "settings.json unchanged by repeat install" [ "$before" = "$after" ]

echo
echo "6. existing unrelated hooks are preserved:"
H6="$TMP/h6"
mkdir -p "$H6"
cat >"$H6/settings.json" <<'JSON'
{
  "model": "sonnet",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 /some/other/guard.py", "timeout": 10 }
        ]
      }
    ]
  }
}
JSON
run_ish "$H6" -- install --apply >/dev/null 2>&1
content="$(cat "$H6/settings.json")"
check "unrelated PreToolUse hook survives" contains "/some/other/guard.py" "$content"
check "model key survives" contains '"model": "sonnet"' "$content"
check "SessionStart was added alongside it" contains "session-start-context.py" "$content"
check "settings.json still valid JSON" python3 -c "import json; json.load(open('$H6/settings.json'))"

echo
echo "7. install backed up the pre-existing settings.json from step 6:"
backup_count="$(find "$H6" -maxdepth 1 -name 'settings.json.bak-*' | wc -l | tr -d ' ')"
check "exactly one backup exists" [ "$backup_count" -eq 1 ]
backup_file="$(find "$H6" -maxdepth 1 -name 'settings.json.bak-*')"
check "backup preserves the original fixture content" contains '"model": "sonnet"' "$(cat "$backup_file")"
check "backup predates our hook addition" not_contains "session-start-context.py" "$(cat "$backup_file")"

echo
echo "8. uninstall — preview by default:"
out="$(run_ish "$H1" -- uninstall 2>&1)"
check "preview says nothing was written" contains "no changes written" "$out"
content="$(cat "$H1/settings.json")"
check "still installed after preview" contains "session-start-context.py" "$content"

echo
echo "9. uninstall --apply removes cleanly:"
out="$(run_ish "$H1" -- uninstall --apply 2>&1)"
status=$?
check "uninstall exits 0" exit_is "$status" 0
content="$(cat "$H1/settings.json")"
check "SessionStart command gone" not_contains "session-start-context.py" "$content"
check "SessionEnd command gone" not_contains "session-end-breadcrumb.py" "$content"
check "uninstall backed up the file" contains "backup" "$out"

echo
echo "10. uninstall leaves unrelated hooks intact:"
run_ish "$H6" -- uninstall --apply >/dev/null 2>&1
content="$(cat "$H6/settings.json")"
check "unrelated PreToolUse hook still present" contains "/some/other/guard.py" "$content"
check "our SessionStart hook is gone" not_contains "session-start-context.py" "$content"
check "settings.json still valid JSON after uninstall" python3 -c "import json; json.load(open('$H6/settings.json'))"

echo
echo "11. uninstall when not installed is a clean no-op:"
out="$(run_ish "$H1" -- uninstall --apply 2>&1)"
check "reports nothing to do" contains "nothing to do" "$out"

echo
echo "12. malformed settings.json is refused, not overwritten:"
H12="$TMP/h12"
mkdir -p "$H12"
printf '{not valid json' >"$H12/settings.json"
before="$(cat "$H12/settings.json")"
out="$(run_ish "$H12" -- install --apply 2>&1)"
status=$?
check "install refuses on invalid JSON" exit_is "$status" 1
after="$(cat "$H12/settings.json")"
check "malformed file left untouched" [ "$before" = "$after" ]

# ---------------------------------------------------------------------------
# PreToolUse guard wiring (#323, #313)
# ---------------------------------------------------------------------------

echo
echo "13. a single guard wires alone, with its declared matcher:"
H13="$TMP/h13"
mkdir -p "$H13"
out="$(run_ish "$H13" -- install --guard codegraph --apply 2>&1)"
status=$?
check "guard install exits 0" exit_is "$status" 0
content="$(cat "$H13/settings.json")"
check "codegraph guard is wired" contains "codegraph-chaining-guard.py" "$content"
check "wired under PreToolUse" contains "PreToolUse" "$content"
check "matcher is the one #309 shipped" contains 'Bash|mcp__.*codegraph.*' "$content"
check "command points at the CLAUDE_HOME symlink, not the checkout" contains "python3 $H13/hooks/codegraph-chaining-guard.py" "$content"
check "no leading ~ survives into settings.json (#312)" not_contains '"command": "python3 ~' "$content"
check "settings.json is valid JSON" python3 -c "import json; json.load(open('$H13/settings.json'))"
check "naming one guard did not wire the others" not_contains "label-hygiene-guard.py" "$content"
check "naming one guard did not wire the session hooks" not_contains "session-start-context.py" "$content"

echo
echo "14. guard install is idempotent:"
before="$(cat "$H13/settings.json")"
out="$(run_ish "$H13" -- install --guard codegraph --apply 2>&1)"
check "second guard install reports nothing to do" contains "nothing to do" "$out"
check "settings.json unchanged" [ "$before" = "$(cat "$H13/settings.json")" ]

echo
echo "15. guards accumulate without disturbing each other:"
run_ish "$H13" -- install --guard label-hygiene --apply >/dev/null 2>&1
content="$(cat "$H13/settings.json")"
check "label-hygiene guard added" contains "label-hygiene-guard.py" "$content"
check "codegraph guard still wired" contains "codegraph-chaining-guard.py" "$content"
check "label-hygiene keeps its own matcher" contains '"matcher": "Bash"' "$content"
check "codegraph keeps its own matcher" contains 'Bash|mcp__.*codegraph.*' "$content"

echo
echo "16. uninstall removes only the guard it was asked to remove:"
run_ish "$H13" -- uninstall --guard codegraph --apply >/dev/null 2>&1
content="$(cat "$H13/settings.json")"
check "codegraph guard removed" not_contains "codegraph-chaining-guard.py" "$content"
check "label-hygiene guard left alone" contains "label-hygiene-guard.py" "$content"
check "settings.json still valid JSON" python3 -c "import json; json.load(open('$H13/settings.json'))"

echo
echo "17. several selectors in one invocation:"
H17="$TMP/h17"
mkdir -p "$H17"
run_ish "$H17" -- install --session --guard nested-notes --apply >/dev/null 2>&1
content="$(cat "$H17/settings.json")"
check "session hook wired" contains "session-start-context.py" "$content"
check "named guard wired" contains "nested-notes-guard.py" "$content"
check "nested-notes matcher covers the MCP path (#264)" contains 'Bash|mcp__.*github.*' "$content"
check "unnamed guard still absent" not_contains "codegraph-chaining-guard.py" "$content"

echo
echo "18. an unknown guard name is a usage error, not a silent no-op:"
H18="$TMP/h18"
mkdir -p "$H18"
out="$(run_ish "$H18" -- install --guard no-such-guard --apply 2>&1)"
status=$?
check "exits 2 (usage error)" exit_is "$status" 2
check "names the valid guards" contains "nested-notes" "$out"
check "wrote nothing" [ ! -f "$H18/settings.json" ]

echo
echo "19. --guard without a name is a usage error:"
out="$(run_ish "$H18" -- install --guard 2>&1)"
status=$?
check "exits 2 (usage error)" exit_is "$status" 2

echo
echo "20. guard wiring previews by default, like everything else:"
H20="$TMP/h20"
mkdir -p "$H20"
out="$(run_ish "$H20" -- install --guard label-hygiene 2>&1)"
check "preview says nothing was written" contains "no changes written" "$out"
check "no settings.json created by a preview" [ ! -f "$H20/settings.json" ]

echo
echo "21. the hook table is the ONE declared place a matcher lives (#323):"
# Every matcher the installer writes must match the wire-up block in the hook's
# own docstring. Retyping a matcher per install is the drift this asserts away.
rows="$(sed -n '/^hook_table()/,/^}/p' "$ISH" | grep -E '^[a-z-]+;')"
check "the table was found and is non-empty" [ -n "$rows" ]
while IFS=';' read -r selector script event matcher; do
  [ -n "$selector" ] || continue
  src="$REPO_ROOT/global/hooks/$script"
  check "$script exists in global/hooks/" [ -f "$src" ]
  [ -f "$src" ] || continue
  # Read the whole module docstring, not a fixed line window (#393). A window
  # is a guess about where the block sits: label-hygiene's wire-up block landed
  # on line 60 of a 60-line window after #388's docstring edit, one line from
  # breaking. Worse, the no-matcher branch below is a `not_contains`, so a block
  # that drifted out of the window would have passed VACUOUSLY — proving the
  # absence of a string in text that no longer held the block at all. A
  # docstring is a structural bound, and its absence is a hard failure.
  doc="$(awk '/"""/ { seen++ } seen >= 1 { print } seen >= 2 { exit }' "$src")"
  check "$script has a module docstring" [ -n "$doc" ]
  check "$script docstring carries a wire-up block" contains '"hooks": {' "$doc"
  if [ -n "$matcher" ]; then
    check "$script docstring declares matcher $matcher" contains "\"matcher\": \"$matcher\"" "$doc"
  else
    check "$script docstring declares no matcher" not_contains '"matcher"' "$doc"
  fi
  # Match the event in its wire-up form (`"SessionEnd": [`), never as a bare
  # word: every one of these hooks names its event in the docstring's opening
  # prose too, so a substring check passed whether or not the block was there.
  check "$script docstring names event $event" contains "\"$event\": [" "$doc"
done <<EOF
$rows
EOF

echo
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
