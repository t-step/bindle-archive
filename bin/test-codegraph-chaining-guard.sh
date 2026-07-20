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
expect allow "prior call was a Read" "$CG_MCP" "$Q" "$TMP/after-read.jsonl"

# Consecutive CodeGraph calls are the pathology this guard exists to stop.
transcript "$TMP/chain-mcp.jsonl" "$CG_MCP=$Q2"
expect deny "prior call was CodeGraph (MCP)" "$CG_MCP" "$Q" "$TMP/chain-mcp.jsonl"

transcript "$TMP/chain-bash.jsonl" "Bash=$BASH_CG"
expect deny "prior call was CodeGraph (Bash)" "$CG_MCP" "$Q" "$TMP/chain-bash.jsonl"

transcript "$TMP/chain-to-bash.jsonl" "$CG_MCP=$Q2"
expect deny "Bash codegraph after MCP codegraph" "Bash" "$BASH_CG" "$TMP/chain-to-bash.jsonl"

# The escape hatch is an explicit, greppable assertion.
transcript "$TMP/chain-ok.jsonl" "$CG_MCP=$Q2"
expect allow "cg-chain-ok marker" "$CG_MCP" \
  '{"query":"cg-chain-ok wide sweep across the auth and billing subsystems"}' \
  "$TMP/chain-ok.jsonl"

# Non-consecutive calls are fine — an intervening tool resets the chain.
transcript "$TMP/interleaved.jsonl" "$CG_MCP=$Q2" 'Grep={"pattern":"HARD_GATES"}'
expect allow "CodeGraph, then Grep, then CodeGraph" "$CG_MCP" "$Q" "$TMP/interleaved.jsonl"

# PreToolUse fires after the call is written to the transcript, so the newest
# entry is usually this very call. Exactly one self-match is dropped.
transcript "$TMP/self-only.jsonl" 'Read={"file_path":"/tmp/a.py"}' "$CG_MCP=$Q"
expect allow "own record is the newest entry" "$CG_MCP" "$Q" "$TMP/self-only.jsonl"

# Dropping only ONE self-match keeps a genuine identical repeat detectable.
transcript "$TMP/repeat.jsonl" "$CG_MCP=$Q" "$CG_MCP=$Q"
expect deny "identical query repeated" "$CG_MCP" "$Q" "$TMP/repeat.jsonl"

# Fails open on anything it cannot parse.
printf 'not json at all\n{"broken":\n' >"$TMP/malformed.jsonl"
expect allow "malformed transcript" "$CG_MCP" "$Q" "$TMP/malformed.jsonl"

# Tools the guard has no opinion about pass straight through.
transcript "$TMP/chain-other.jsonl" "$CG_MCP=$Q2"
expect allow "non-CodeGraph tool" "Read" '{"file_path":"/tmp/a.py"}' "$TMP/chain-other.jsonl"
expect allow "unrelated Bash command" "Bash" '{"command":"grep -rn HARD_GATES ."}' \
  "$TMP/chain-other.jsonl"

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
