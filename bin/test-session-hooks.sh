#!/usr/bin/env bash
#
# test-session-hooks.sh — self-test for global/hooks/session-start-context.py
# and global/hooks/session-end-breadcrumb.py.
#
# Pipes synthesized SessionStart/SessionEnd payloads through the hooks
# against a throwaway git repo and notes vault. Never touches the real
# ~/.bindle, ~/.claude, TMPDIR marker namespace clashes aside (session_id is
# randomized per run), or any real git repo.
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_HOOK="$REPO_ROOT/global/hooks/session-start-context.py"
END_HOOK="$REPO_ROOT/global/hooks/session-end-breadcrumb.py"
PASS=0
FAIL=0

check() { # check "description" command...
  local desc="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"
    PASS=$((PASS + 1))
  else
    printf '  ✗ %s\n' "$desc"
    FAIL=$((FAIL + 1))
  fi
}

contains() { grep -qF -- "$1" <<<"$2"; }

start_payload() { # start_payload session_id cwd [source]
  python3 - "$1" "$2" "${3:-startup}" <<'PY'
import json, sys
print(json.dumps({"hook_event_name": "SessionStart", "session_id": sys.argv[1], "cwd": sys.argv[2], "source": sys.argv[3]}))
PY
}

end_payload() { # end_payload session_id cwd [reason]
  python3 - "$1" "$2" "${3:-other}" <<'PY'
import json, sys
print(json.dumps({"hook_event_name": "SessionEnd", "session_id": sys.argv[1], "cwd": sys.argv[2], "reason": sys.argv[3]}))
PY
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

REPO="$TMP/My_Proj"
mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@example.com
git -C "$REPO" config user.name t
touch "$REPO/a.txt"
git -C "$REPO" add a.txt
git -C "$REPO" commit -q -m init

VAULT="$TMP/vault"
mkdir -p "$VAULT"

# ===========================================================================
echo "1. SessionStart injects additionalContext:"
SID="sid-$$-1"
out="$(start_payload "$SID" "$REPO" | env BINDLE_NOTES_DIR="$VAULT" python3 "$START_HOOK")"
check "emits hookSpecificOutput" contains '"hookSpecificOutput"' "$out"
check "names the SessionStart event" contains '"hookEventName": "SessionStart"' "$out"
check "additionalContext has the slugified project" contains "project: my-proj" "$out"
check "additionalContext has the notes home" contains "$VAULT" "$out"

echo
echo "2. SessionStart drops a start marker keyed by session_id:"
MARKER="${TMPDIR:-/tmp}/bindle-session-$SID.json"
check "marker file exists" [ -f "$MARKER" ]
check "marker records the repo root" contains "$REPO" "$(cat "$MARKER" 2>/dev/null || true)"

echo
echo "3. wrong hook_event_name is ignored:"
out="$(
  python3 - "$REPO" <<'PY' | env BINDLE_NOTES_DIR="$VAULT" python3 "$START_HOOK"
import json, sys
print(json.dumps({"hook_event_name": "PreToolUse", "session_id": "sid-wrong", "cwd": sys.argv[1]}))
PY
)"
check "no output for a non-SessionStart event" [ -z "$out" ]

echo
echo "4. SessionStart on a non-git cwd degrades silently:"
PLAIN="$TMP/plain"
mkdir -p "$PLAIN"
out="$(start_payload "sid-plain" "$PLAIN" | env BINDLE_NOTES_DIR="$VAULT" python3 "$START_HOOK")"
check "still emits additionalContext (session-context.sh degrades, not the hook)" contains "not a git repo" "$out"

echo
echo "5. commit made, then SessionEnd writes a breadcrumb with the right count:"
echo "change" >>"$REPO/a.txt"
git -C "$REPO" add a.txt
git -C "$REPO" commit -q -m second
out="$(end_payload "$SID" "$REPO" | env BINDLE_NOTES_DIR="$VAULT" python3 "$END_HOOK")"
check "SessionEnd prints nothing (pure script, no model talk-back)" [ -z "$out" ]
LOG="$VAULT/projects/my-proj/breadcrumbs.log"
check "breadcrumb log was created under the slugified project dir" [ -f "$LOG" ]
check "breadcrumb reports 1 commit this session" contains "commits_this_session=1" "$(cat "$LOG")"
check "breadcrumb reports the branch" contains "branch=" "$(cat "$LOG")"
check "breadcrumb reports the reason" contains "reason=other" "$(cat "$LOG")"

echo
echo "6. SessionEnd cleans up the marker:"
check "marker file removed" [ ! -f "$MARKER" ]

echo
echo "7. SessionEnd without a prior marker reports unknown commits, doesn't fail:"
out="$(
  end_payload "sid-no-marker" "$REPO" | env BINDLE_NOTES_DIR="$VAULT" python3 "$END_HOOK"
  echo "exit=$?"
)"
check "exits cleanly" contains "exit=0" "$out"
check "second breadcrumb line appended" [ "$(wc -l <"$LOG" | tr -d ' ')" -eq 2 ]
check "unknown commits when no marker" contains "commits_this_session=unknown" "$(tail -1 "$LOG")"

echo
echo "8. SessionEnd on a non-git cwd writes nothing (no durable repo to record):"
before="$(find "$VAULT" -type f | sort)"
end_payload "sid-plain-end" "$PLAIN" | env BINDLE_NOTES_DIR="$VAULT" python3 "$END_HOOK" >/dev/null
after="$(find "$VAULT" -type f | sort)"
check "vault file set unchanged" [ "$before" = "$after" ]

echo
echo "9. malformed stdin never crashes either hook:"
out_s="$(echo 'not json' | python3 "$START_HOOK" 2>&1)"
status_s=$?
out_e="$(echo 'not json' | python3 "$END_HOOK" 2>&1)"
status_e=$?
check "SessionStart hook exits 0 on garbage input" [ "$status_s" -eq 0 ]
check "SessionStart hook prints nothing on garbage input" [ -z "$out_s" ]
check "SessionEnd hook exits 0 on garbage input" [ "$status_e" -eq 0 ]
check "SessionEnd hook prints nothing on garbage input" [ -z "$out_e" ]

echo
echo "passed $PASS, failed $FAIL"
[ "$FAIL" -eq 0 ]
