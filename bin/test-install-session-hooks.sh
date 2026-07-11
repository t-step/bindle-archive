#!/usr/bin/env bash
#
# test-install-session-hooks.sh — exercise bin/install-session-hooks.sh end
# to end against throwaway --home directories. Never touches your real
# ~/.claude/settings.json.
#
# Usage: bin/test-install-session-hooks.sh
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISH="$REPO_ROOT/bin/install-session-hooks.sh"

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
check "reports not installed" contains "not installed" "$out"

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

echo
echo "4. status after install:"
out="$(run_ish "$H1" -- status 2>&1)"
check "reports installed" contains "installed (in" "$out"

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

echo
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
