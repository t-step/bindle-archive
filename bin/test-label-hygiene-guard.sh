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

# Extracts the commands a denial SUGGESTS. Convention, shared with check_merge:
# a suggested command occupies its own line and stripped starts with `gh `.
# Prose that merely names a subcommand in backticks is not on its own line and
# so is not mistaken for advice.
suggested_commands() { # suggested_commands <guard-output>
  python3 - "$1" <<'PY'
import json, sys
try:
    reason = json.loads(sys.argv[1])["hookSpecificOutput"]["permissionDecisionReason"]
except Exception:
    sys.exit(0)
for line in reason.splitlines():
    if line.strip().startswith("gh "):
        print(line.strip())
PY
}

# Asserts every suggested command is a shape `gh` accepts (#366). `gh issue
# close` has no --remove-label flag, so advice pairing them cannot be run — and
# neither a deny-decision assertion nor a message-substring assertion can see
# that. Flag tables are transcribed from `gh issue close --help` and `gh issue
# edit --help` (gh 2.96.0); the suite stays hermetic, so the stub `gh` on PATH
# cannot be asked at runtime.
expect_suggested_commands_runnable() { # <name> <denied-command> [cwd]
  local name="$1" cmd="$2" cwd="${3:-$REPO}" out cmds bad
  out="$(payload "$cmd" "$cwd" | python3 "$GUARD")"
  cmds="$(suggested_commands "$out")"
  if [ -z "$cmds" ]; then
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (denial suggested no runnable command at all)" >&2
    return
  fi
  bad="$(
    python3 - "$cmds" <<'PY'
import sys

FLAGS = {
    ("issue", "close"): {"-c", "--comment", "--duplicate-of", "-r", "--reason",
                         "-R", "--repo"},
    ("issue", "edit"): {"--add-assignee", "--add-blocked-by", "--add-blocking",
                        "--add-label", "--add-project", "--add-sub-issue",
                        "-b", "--body", "-F", "--body-file", "-m", "--milestone",
                        "--parent", "--remove-assignee", "--remove-blocked-by",
                        "--remove-blocking", "--remove-label",
                        "--remove-milestone", "--remove-parent",
                        "--remove-project", "--remove-sub-issue",
                        "--remove-type", "-t", "--title", "--type",
                        "-R", "--repo"},
}

for line in sys.argv[1].splitlines():
    parts = line.split()
    if len(parts) < 3:
        print(f"{line!r}: not a complete gh invocation")
        continue
    key = (parts[1], parts[2])
    known = FLAGS.get(key)
    if known is None:
        print(f"{line!r}: no flag table for `gh {key[0]} {key[1]}`")
        continue
    for tok in parts[3:]:
        flag = tok.split("=", 1)[0]
        if flag.startswith("-") and flag not in known:
            print(f"{line!r}: `gh {key[0]} {key[1]}` has no {flag}")
PY
  )"
  if [ -n "$bad" ]; then
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name" >&2
    while IFS= read -r line; do echo "    $line" >&2; done <<<"$bad"
    return
  fi
  PASS=$((PASS + 1))
  echo "  ok: $name"
}

# Runs the suggested command ahead of the original and asserts the guard then
# allows it — proving the advice is not just well-formed but actually unblocks.
expect_suggested_command_unblocks() { # <name> <denied-command> [cwd]
  local name="$1" cmd="$2" cwd="${3:-$REPO}" out first fixed
  out="$(payload "$cmd" "$cwd" | python3 "$GUARD")"
  first="$(suggested_commands "$out" | head -1)"
  if [ -z "$first" ]; then
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (denial suggested no command to run)" >&2
    return
  fi
  fixed="$first && $cmd"
  out="$(payload "$fixed" "$cwd" | python3 "$GUARD")"
  if grep -q '"permissionDecision": "deny"' <<<"$out"; then
    FAIL=$((FAIL + 1))
    echo "  FAIL: $name (guard still denied after its own advice: $fixed)" >&2
  else
    PASS=$((PASS + 1))
    echo "  ok: $name"
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
# `gh issue close` has no --remove-label flag, so the in-band escape is a real
# `gh issue edit` chained ahead of it — which is what the REMOVE_LABEL parse
# actually recognizes (#366; #350's "dead code" reading was wrong).
expect allow "R1 close chained after a runnable gh issue edit --remove-label" \
  "gh issue edit 266 --remove-label 'status: ready' && gh issue close 266"
expect allow "R1 close, issue has no status: label" "gh issue close 900"
expect_msg "status: ready" "R1 names the offending label" "gh issue close 266"
expect_suggested_commands_runnable "R1 remediation is a runnable gh shape (#366)" \
  "gh issue close 266"
expect_suggested_command_unblocks "R1 remediation actually unblocks the close (#366)" \
  "gh issue close 266"
expect_suggested_commands_runnable "R2 remediation is a runnable gh shape" \
  "gh pr merge 320 --squash"

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

# --- #388: a gh literal quoted as inert data is not an invocation ------------
# The guard matches only at a COMMAND POSITION — start of the command, or after
# a newline / && / || / ; / | / (. Text that merely CONTAINS a matching command
# mutates nothing, and denying it blocked a read-only probe during #366.
expect allow "inert: close inside a python3 -c string literal" \
  "python3 -c \"print('gh issue close 266')\""
expect allow "inert: close inside an echo" \
  "echo \"remediation: gh issue close 266\""
expect allow "inert: close in a comment" \
  "# gh issue close 266"
expect allow "inert: merge as a grep pattern" \
  "grep -rn 'gh pr merge 320' bin/"
expect allow "inert: gh api close bypass quoted as data" \
  "echo \"gh api -X PATCH repos/o/r/issues/266 -f state=closed\""
expect allow "inert: R3 edit quoted as data" \
  "echo \"gh issue edit 901 --add-label 'status: ready'\""

# A real invocation stays denied in every form the guard catches today.
expect deny "real: close after &&" "git fetch --prune && gh issue close 266"
expect deny "real: close after ;" "git fetch --prune; gh issue close 266"
expect deny "real: close after ||" "git fetch --prune || gh issue close 266"
expect deny "real: close on its own line" $'git fetch --prune\ngh issue close 266'
expect deny "real: close with leading whitespace" "   gh issue close 266"
expect deny "real: close behind an env-var prefix" \
  "GH_HOST=github.com gh issue close 266"
expect deny "real: close in a subshell" "(gh issue close 266)"
expect deny "real: merge after &&" "make check && gh pr merge 320 --squash"
expect deny "real: api close bypass after &&" \
  "git fetch && gh api -X PATCH repos/o/r/issues/266 -f state=closed"
expect deny "real: R3 edit after &&" \
  "git fetch && gh issue edit 901 --add-label 'status: ready'"

# The escape hatch only counts when it is a real command, not quoted text —
# otherwise inert data becomes a way to talk the guard out of a real deny.
expect deny "escape: --remove-label quoted as data does not unblock a close" \
  "echo \"--remove-label 'status: ready'\" && gh issue close 266"

# Documented residual: a heredoc line that BEGINS with gh reads as a command
# position and is still denied. The marker is the escape.
expect deny "residual: heredoc line beginning with gh is still denied" \
  $'cat <<EOF\ngh issue close 266\nEOF'
expect allow "escape: the inert marker disarms the guard" \
  $'# label-hygiene-guard: inert\ncat <<EOF\ngh issue close 266\nEOF'

# --- #399: every segment is evaluated, not just the first one that matches ---
# The dispatch loop used to return after the first segment matching ANY rule, so
# a harmless leading segment consumed the whole command line and the rule that
# WOULD have denied a later segment never ran.
expect deny "every-segment: R1 close after an allowed R3 edit segment" \
  "gh issue edit 902 --add-label 'status: ready' && gh issue close 266"
expect deny "every-segment: R2 merge after an allowed R3 edit segment" \
  "gh issue edit 902 --add-label 'status: in-progress' && gh pr merge 320 --squash"
expect deny "every-segment: R3 edit after an allowed close segment" \
  "gh issue close 900 && gh issue edit 901 --add-label 'status: ready'"
expect deny "every-segment: R1 close after an allowed gh api non-close" \
  "gh api repos/o/r/issues/266 && gh issue close 266"

# --- #399: the escape hatch is keyed by (issue, label), not the label alone ---
# The removed-label set used to be flat, so removing a label from ANY issue
# unblocked closing a DIFFERENT one. These cases must stay denied under a mutant
# that discards the edit's issue number — the pre-existing escape-hatch tests
# above all use the CORRECT number and cannot see that mutation.
expect deny "escape: --remove-label on a DIFFERENT issue does not unblock a close" \
  "gh issue edit 900 --remove-label 'status: ready' && gh issue close 266"
expect deny "escape: --remove-label on a different issue, api close bypass" \
  "gh issue edit 900 --remove-label 'status: ready' && gh api -X PATCH repos/o/r/issues/266 -f state=closed"

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
