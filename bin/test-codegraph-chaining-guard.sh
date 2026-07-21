#!/usr/bin/env bash
#
# test-codegraph-chaining-guard.sh — self-test for
# global/hooks/codegraph-chaining-guard.py.
#
# Pipes synthesized PreToolUse payloads through the hook and asserts the
# allow/deny decision. Hermetic: every transcript is a fixture written to a
# throwaway temp dir, never a real ~/.claude transcript.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$REPO_ROOT/global/hooks/codegraph-chaining-guard.py"
PASS=0
FAIL=0

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export BINDLE_CODEGRAPH_GUARD_STATE_DIR="$TMP/state"

CG_MCP="mcp__codegraph__codegraph_explore"

# transcript <file> <name:json-input> ... — one assistant tool_use record per arg.
transcript() {
  local out="$1"
  shift
  python3 - "$out" "$@" <<'PY'
import json, sys
out, *entries = sys.argv[1:]
with open(out, "w", encoding="utf-8") as fh:
    for entry in entries:
        name, _, raw = entry.partition("=")
        block = {"type": "tool_use", "name": name, "input": json.loads(raw or "{}")}
        fh.write(json.dumps({"type": "assistant", "message": {"content": [block]}}) + "\n")
PY
}

# payload <tool_name> <tool_input-json> <transcript_path>
payload() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
name, raw, path = sys.argv[1:4]
print(json.dumps({
    "hook_event_name": "PreToolUse",
    "tool_name": name,
    "tool_input": json.loads(raw),
    "transcript_path": path,
}))
PY
}

# expect <allow|deny> <name> <tool_name> <tool_input-json> <transcript_path> [guard]
expect() {
  local want="$1" label="$2" tool="$3" input="$4" path="$5" guard="${6:-$GUARD}"
  local out got
  out="$(payload "$tool" "$input" "$path" | python3 "$guard")"
  if grep -q '"permissionDecision": "deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [[ "$got" == "$want" ]]; then
    PASS=$((PASS + 1))
    echo "  ok: $label"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $label (wanted $want, got $got)" >&2
  fi
}

echo "codegraph-chaining-guard self-test"

Q='{"query":"where is the registry dispatched"}'
Q2='{"query":"trace the gate list"}'
BASH_CG='{"command":"codegraph explore \"HARD_GATES\""}'

# An empty or absent history never blocks the first call.
: >"$TMP/empty.jsonl"
expect allow "empty transcript" "$CG_MCP" "$Q" "$TMP/empty.jsonl"
expect allow "transcript path missing" "$CG_MCP" "$Q" "$TMP/does-not-exist.jsonl"
expect allow "no transcript_path field" "$CG_MCP" "$Q" ""

# A non-CodeGraph predecessor is the normal, intended usage.
transcript "$TMP/after-read.jsonl" 'Read={"file_path":"/tmp/a.py"}'
expect allow "observe a Read predecessor" "Read" '{"file_path":"/tmp/a.py"}' "$TMP/after-read.jsonl"
expect allow "prior call was a Read" "$CG_MCP" "$Q" "$TMP/after-read.jsonl"

# Consecutive CodeGraph calls are the pathology this guard exists to stop.
transcript "$TMP/chain-mcp.jsonl" "$CG_MCP=$Q2"
expect allow "first MCP CodeGraph call" "$CG_MCP" "$Q2" "$TMP/chain-mcp.jsonl"
expect deny "prior call was CodeGraph (MCP)" "$CG_MCP" "$Q" "$TMP/chain-mcp.jsonl"

transcript "$TMP/chain-bash.jsonl" "Bash=$BASH_CG"
expect allow "first Bash CodeGraph call" "Bash" "$BASH_CG" "$TMP/chain-bash.jsonl"
expect deny "prior call was CodeGraph (Bash)" "$CG_MCP" "$Q" "$TMP/chain-bash.jsonl"

transcript "$TMP/chain-to-bash.jsonl" "$CG_MCP=$Q2"
expect allow "first MCP call before Bash CodeGraph" "$CG_MCP" "$Q2" "$TMP/chain-to-bash.jsonl"
expect deny "Bash codegraph after MCP codegraph" "Bash" "$BASH_CG" "$TMP/chain-to-bash.jsonl"

# The escape hatch is an explicit, greppable assertion.
transcript "$TMP/chain-ok.jsonl" "$CG_MCP=$Q2"
expect allow "first CodeGraph call before cg-chain-ok" "$CG_MCP" "$Q2" "$TMP/chain-ok.jsonl"
expect allow "cg-chain-ok marker" "$CG_MCP" \
  '{"query":"cg-chain-ok wide sweep across the auth and billing subsystems"}' \
  "$TMP/chain-ok.jsonl"

# Non-consecutive calls are fine — an intervening tool resets the chain.
transcript "$TMP/interleaved.jsonl" "$CG_MCP=$Q2" 'Grep={"pattern":"HARD_GATES"}'
expect allow "first CodeGraph call before Grep" "$CG_MCP" "$Q2" "$TMP/interleaved.jsonl"
expect allow "intervening Grep is observed" "Grep" '{"pattern":"HARD_GATES"}' \
  "$TMP/interleaved.jsonl"
expect allow "CodeGraph, then Grep, then CodeGraph" "$CG_MCP" "$Q" "$TMP/interleaved.jsonl"

# The transcript can contain this very call; the state path, not transcript
# contents, determines whether there is a predecessor.
transcript "$TMP/self-only.jsonl" 'Read={"file_path":"/tmp/a.py"}' "$CG_MCP=$Q"
expect allow "own record is the newest entry" "$CG_MCP" "$Q" "$TMP/self-only.jsonl"

# A genuine identical repeat is still detectable.
transcript "$TMP/repeat.jsonl" "$CG_MCP=$Q" "$CG_MCP=$Q"
expect allow "first identical query" "$CG_MCP" "$Q" "$TMP/repeat.jsonl"
expect deny "identical query repeated" "$CG_MCP" "$Q" "$TMP/repeat.jsonl"

# Fails open on anything it cannot parse.
printf 'not json at all\n{"broken":\n' >"$TMP/malformed.jsonl"
expect allow "malformed transcript" "$CG_MCP" "$Q" "$TMP/malformed.jsonl"

# Tools the guard has no opinion about pass straight through.
transcript "$TMP/chain-other.jsonl" "$CG_MCP=$Q2"
expect allow "non-CodeGraph tool" "Read" '{"file_path":"/tmp/a.py"}' "$TMP/chain-other.jsonl"
expect allow "unrelated Bash command" "Bash" '{"command":"grep -rn HARD_GATES ."}' \
  "$TMP/chain-other.jsonl"

# The replacement design must not need transcript contents. The hook is wired
# for every tool call and keeps only the immediately preceding tool in temp
# state keyed by transcript_path.
: >"$TMP/state-empty.jsonl"
expect allow "state: first CodeGraph call is allowed" "$CG_MCP" "$Q" "$TMP/state-empty.jsonl"
expect deny "state: second CodeGraph call is denied without transcript contents" \
  "$CG_MCP" "$Q2" "$TMP/state-empty.jsonl"

: >"$TMP/state-reset.jsonl"
expect allow "state: first CodeGraph call before reset" "$CG_MCP" "$Q" "$TMP/state-reset.jsonl"
expect allow "state: intervening Read updates the previous tool" \
  "Read" '{"file_path":"/tmp/a.py"}' "$TMP/state-reset.jsonl"
expect allow "state: non-CodeGraph predecessor resets the chain" \
  "$CG_MCP" "$Q2" "$TMP/state-reset.jsonl"

: >"$TMP/state-subagent-a.jsonl"
: >"$TMP/state-subagent-b.jsonl"
expect allow "state: subagent A first CodeGraph call" "$CG_MCP" "$Q" "$TMP/state-subagent-a.jsonl"
expect allow "state: subagent B has isolated first CodeGraph call" \
  "$CG_MCP" "$Q2" "$TMP/state-subagent-b.jsonl"
expect deny "state: subagent A still sees its own previous CodeGraph call" \
  "$CG_MCP" "$Q2" "$TMP/state-subagent-a.jsonl"

OLD_STATE_DIR="$BINDLE_CODEGRAPH_GUARD_STATE_DIR"
export BINDLE_CODEGRAPH_GUARD_STATE_DIR="$TMP/unreadable-state"
: >"$TMP/state-unreadable.jsonl"
expect allow "state: first CodeGraph before unreadable state" "$CG_MCP" "$Q" "$TMP/state-unreadable.jsonl"
chmod 000 "$BINDLE_CODEGRAPH_GUARD_STATE_DIR"/codegraph-chain-*.json
expect allow "state: unreadable state fails open" "$CG_MCP" "$Q2" "$TMP/state-unreadable.jsonl"
chmod 600 "$BINDLE_CODEGRAPH_GUARD_STATE_DIR"/codegraph-chain-*.json
export BINDLE_CODEGRAPH_GUARD_STATE_DIR="$OLD_STATE_DIR"

mkdir -p "$BINDLE_CODEGRAPH_GUARD_STATE_DIR"
STALE="$BINDLE_CODEGRAPH_GUARD_STATE_DIR/codegraph-chain-stale.json"
printf '{"tool_name":"%s","tool_input":%s}\n' "$CG_MCP" "$Q" >"$STALE"
touch -t 200001010000 "$STALE"
expect allow "state: stale files do not block a call" "$CG_MCP" "$Q" "$TMP/state-cleanup.jsonl"
if [[ -e "$STALE" ]]; then
  echo "  FAIL: state: stale file was not cleaned up" >&2
  FAIL=$((FAIL + 1))
else
  PASS=$((PASS + 1))
  echo "  ok: state: stale file was cleaned up"
fi

# Mutation pass: the repo rule is that a new gate must be proven failable.
# Inverting the consecutive check must flip every deny case to allow.
MUTANT="$TMP/mutant.py"
sed 's/^    if previous is None or not is_codegraph(previous\[0\], previous\[1\]):$/    if previous is not None and is_codegraph(previous[0], previous[1]):/' \
  "$GUARD" >"$MUTANT"
if cmp -s "$GUARD" "$MUTANT"; then
  echo "  FAIL: mutation pass — the consecutive check did not match; update the sed" >&2
  FAIL=$((FAIL + 1))
else
  echo "  (mutation: consecutive check inverted)"
  expect allow "mutant lets an MCP chain through" "$CG_MCP" "$Q" "$TMP/chain-mcp.jsonl" "$MUTANT"
  expect allow "mutant lets a Bash chain through" "$CG_MCP" "$Q" "$TMP/chain-bash.jsonl" "$MUTANT"
  expect allow "mutant lets a repeat through" "$CG_MCP" "$Q" "$TMP/repeat.jsonl" "$MUTANT"
fi

echo "codegraph-chaining-guard: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
