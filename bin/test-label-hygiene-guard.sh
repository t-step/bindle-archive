#!/usr/bin/env bash
#
# test-label-hygiene-guard.sh — self-test for global/hooks/label-hygiene-guard.py.
#
# Pipes synthesized PreToolUse payloads through the hook and asserts the
# allow/deny decision. Hermetic: a stub `gh` on PATH answers from canned JSON
# fixtures, so no test here reaches the network or a real repository. A fixture
# the stub cannot find makes it exit non-zero, which is also how the fail-open
# case is exercised.
#
set -euo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so the fixture-repo git calls
# below would hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$REPO_ROOT/global/hooks/label-hygiene-guard.py"
PASS=0
FAIL=0

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FIXTURES="$TMP/fixtures"
STUBBIN="$TMP/bin"
mkdir -p "$FIXTURES" "$STUBBIN"

# --- stub gh ----------------------------------------------------------------
# Answers `gh issue view N --json ...` and `gh pr view N --json ...` from
# $GH_FIXTURES/{issue,pr}-N.json. Anything else, or a missing fixture, exits 1 —
# which is exactly the "API unreachable" shape the guard must fail open on.
cat >"$STUBBIN/gh" <<'STUB'
#!/usr/bin/env bash
kind=""
case "${1:-}" in
  issue) kind=issue ;;
  pr) kind=pr ;;
  *) exit 1 ;;
esac
[ "${2:-}" = "view" ] || exit 1
num="${3:-}"
f="$GH_FIXTURES/$kind-$num.json"
[ -f "$f" ] || exit 1
cat "$f"
STUB
chmod +x "$STUBBIN/gh"

export GH_FIXTURES="$FIXTURES"
export PATH="$STUBBIN:$PATH"

# --- fixture repo (carries the contract file the guard gates on) -------------
REPO="$TMP/repo"
mkdir -p "$REPO/docs"
git -C "$REPO" init -q
echo "# Issue tracking" >"$REPO/docs/issue-tracking.md"
git -C "$REPO" add -A
git -C "$REPO" -c user.email=t@e -c user.name=t commit -qm init

# A repo WITHOUT the contract file — the guard must no-op here.
BARE="$TMP/norules"
mkdir -p "$BARE"
git -C "$BARE" init -q

issue_fixture() { # issue_fixture <num> <state> <label,label,...>
  local num="$1" state="$2" labels="$3"
  python3 - "$FIXTURES/issue-$num.json" "$state" "$labels" <<'PY'
import json, sys
path, state, labels = sys.argv[1], sys.argv[2], sys.argv[3]
names = [x for x in labels.split(",") if x]
json.dump({"state": state, "labels": [{"name": n} for n in names]}, open(path, "w"))
PY
}

pr_fixture() { # pr_fixture <num> <body> <commit-message>
  local num="$1" body="$2" msg="$3"
  python3 - "$FIXTURES/pr-$num.json" "$body" "$msg" <<'PY'
import json, sys
path, body, msg = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump({"body": body, "commits": [{"messageHeadline": msg.split("\n")[0],
                                      "messageBody": "\n".join(msg.split("\n")[1:])}]},
          open(path, "w"))
PY
}

payload() { # payload <command> [cwd]
  python3 - "$1" "${2:-$REPO}" <<'PY'
import json, sys
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}, "cwd": sys.argv[2]}))
PY
}

expect() { # expect <allow|deny> <name> <command> [cwd]
  local want="$1" name="$2" cmd="$3" cwd="${4:-$REPO}"
  local out got
  out="$(payload "$cmd" "$cwd" | python3 "$GUARD")"
  if grep -q '"permissionDecision": "deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [[ "$got" == "$want" ]]; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (wanted $want, got $got)" >&2
  fi
}

expect_msg() { # expect_msg <substring> <name> <command> [cwd]
  local want="$1" name="$2" cmd="$3" cwd="${4:-$REPO}"
  local out
  out="$(payload "$cmd" "$cwd" | python3 "$GUARD")"
  if grep -qF -- "$want" <<<"$out"; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (message lacked '$want')" >&2
  fi
}

# Runs the guard's OWN remediation instead of matching its text (#364). Denies
# whose advice cannot be followed are the recurring defect in this hook, and a
# message-substring assertion cannot see that: it passes on advice that errors.
expect_remediation_allows() { # expect_remediation_allows <name> <denied-command> [cwd]
  local name="$1" cmd="$2" cwd="${3:-$REPO}"
  local out flags fixed got
  out="$(payload "$cmd" "$cwd" | python3 "$GUARD")"
  flags="$(
    python3 - "$out" <<'PY'
import json, re, sys
try:
    reason = json.loads(sys.argv[1])["hookSpecificOutput"]["permissionDecisionReason"]
except Exception:
    sys.exit(0)
m = re.search(r"in the same command:\s*(.+?)\.?$", reason)
print(m.group(1).strip() if m else "")
PY
  )"
  if [ -z "$flags" ]; then
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (guard emitted no in-command remediation to run)" >&2
    return
  fi
  fixed="$cmd $flags"
  out="$(payload "$fixed" "$cwd" | python3 "$GUARD")"
  if grep -q '"permissionDecision": "deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [[ "$got" == allow ]]; then
    PASS=$((PASS + 1))
    echo "  ok: $name"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (guard denied its own remediation: $fixed)" >&2
  fi
}

echo "label-hygiene-guard self-test"

# --- fixtures ---------------------------------------------------------------
issue_fixture 266 OPEN "type: feat,status: ready,priority: normal"
issue_fixture 900 OPEN "type: chore,priority: normal" # no status: label
issue_fixture 901 OPEN "type: chore,status: triage"   # triage, no priority
issue_fixture 902 OPEN "type: chore,priority: now"    # has priority
pr_fixture 320 "Adds the thing. Resolves #266" "feat: add the thing"
pr_fixture 321 "Adds the thing, no keyword here." "feat: add the thing (closes #266)"
pr_fixture 322 "Adds the thing. Resolves #900" "feat: add the thing"
pr_fixture 323 "Adds the thing. No issue referenced." "feat: add the thing"

# --- gate -------------------------------------------------------------------
expect allow "no contract file: guard no-ops" "gh issue close 266" "$BARE"
expect allow "non-gh command" "ls -la"
expect allow "gh read-only" "gh issue view 266 --json labels"

# --- R1: closing an issue that still carries a status: label ----------------
expect deny "R1 close with status: label" "gh issue close 266"
expect allow "R1 close with matching --remove-label" \
  "gh issue close 266 --remove-label 'status: ready'"
expect allow "R1 close, issue has no status: label" "gh issue close 900"
expect_msg "status: ready" "R1 names the offending label" "gh issue close 266"

# --- R1 bypass: gh api PATCH state=closed -----------------------------------
expect deny "R1 gh api state=closed bypass" \
  "gh api -X PATCH repos/o/r/issues/266 -f state=closed"

# --- R2: merging a PR that closes a labeled issue ---------------------------
expect deny "R2 merge, closing keyword in PR body" "gh pr merge 320 --squash"
expect deny "R2 merge, closing keyword in COMMIT message" "gh pr merge 321 --squash"
expect allow "R2 merge, closed issue has no status: label" "gh pr merge 322 --squash"
expect allow "R2 merge, no closing keyword anywhere" "gh pr merge 323 --squash"

# --- R3: leaving triage without a priority ----------------------------------
expect deny "R3 add non-triage status, no priority" \
  "gh issue edit 901 --add-label 'status: ready'"
expect allow "R3 add non-triage status, has priority" \
  "gh issue edit 902 --add-label 'status: in-progress'"
expect allow "R3 add status: triage needs no priority" \
  "gh issue edit 901 --add-label 'status: triage'"
expect allow "R3 unrelated label edit" \
  "gh issue edit 901 --add-label 'type: docs'"
expect allow "R3 priority supplied in the SAME command (#364)" \
  "gh issue edit 901 --add-label 'status: ready' --add-label 'priority: normal'"
expect allow "R3 priority added, status removed and re-added in one command" \
  "gh issue edit 901 --remove-label 'status: triage' --add-label 'status: blocked' --add-label 'priority: normal'"
expect_remediation_allows "R3 the guard's own remediation is accepted (#364)" \
  "gh issue edit 901 --add-label 'status: ready'"

# --- fail open --------------------------------------------------------------
# Issue 999 has no fixture, so the stub gh exits 1 — the API-unreachable shape.
expect allow "fail open when gh errors" "gh issue close 999"
expect allow "fail open on merge when gh errors" "gh pr merge 999 --squash"

echo
if [ "$FAIL" -gt 0 ]; then
  echo "  $PASS passed, $FAIL FAILED" >&2
  exit 1
fi
echo "  all $PASS checks pass"
