#!/usr/bin/env bash
# shellcheck disable=SC2015
#
# test-subagent-concurrency-guard.sh — self-test for
# global/hooks/subagent-concurrency-guard.py.
#
# Pipes synthesized PreToolUse/PostToolUse payloads through the guard and
# asserts the allow/deny decision and slot-file side effects. Hermetic: every
# transcript and every piece of guard state is a fixture under a throwaway
# temp dir — HOME is overridden for every guard invocation so the guard's
# real ~/.claude/bindle/state/subagent-concurrency is never touched.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$REPO_ROOT/global/hooks/subagent-concurrency-guard.py"
PASS=0
FAIL=0

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_HOME="$TMP/home"
mkdir -p "$FAKE_HOME"
SLOTS_DIR="$FAKE_HOME/.claude/bindle/state/subagent-concurrency/slots"

# transcript <file> <name>[:<tool_use_id>]=<json-input> ... — one assistant
# tool_use record per arg. tool_use_id defaults to a fixed placeholder when
# omitted (fine for non-Agent entries, where the guard never reads the id).
transcript() {
  local out="$1"
  shift
  python3 - "$out" "$@" <<'PY'
import json, sys
out, *entries = sys.argv[1:]
with open(out, "w", encoding="utf-8") as fh:
    for entry in entries:
        head, _, raw = entry.partition("=")
        name, _, tool_id = head.partition(":")
        block = {
            "type": "tool_use",
            "name": name,
            "id": tool_id or "toolu_test",
            "input": json.loads(raw or "{}"),
        }
        fh.write(json.dumps({"type": "assistant", "message": {"content": [block]}}) + "\n")
PY
}

# payload <hook_event_name> <tool_name> <transcript_path>
payload() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
event, name, path = sys.argv[1:4]
print(json.dumps({
    "hook_event_name": event,
    "tool_name": name,
    "tool_input": {},
    "transcript_path": path,
}))
PY
}

# run <hook_event_name> <tool_name> <transcript_path> — prints guard stdout.
run() {
  payload "$1" "$2" "$3" | HOME="$FAKE_HOME" python3 "$GUARD"
}

# expect <allow|deny> <label> <hook_event_name> <tool_name> <transcript_path>
expect() {
  local want="$1" label="$2" event="$3" tool="$4" path="$5"
  local out got
  out="$(run "$event" "$tool" "$path")"
  if grep -q '"permissionDecision": "deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [[ "$got" == "$want" ]]; then
    PASS=$((PASS + 1))
    echo "  ok: $label"
  else
    FAIL=$((FAIL + 1))
    echo "  FAIL: $label (wanted $want, got $got)" >&2
  fi
}

slot_count() { find "$SLOTS_DIR" -type f 2>/dev/null | wc -l | tr -d ' '; }

age_slot() { # age_slot <id> <seconds-old>
  python3 -c "import os,time,sys; p=sys.argv[1]; t=time.time()-float(sys.argv[2]); os.utime(p,(t,t))" \
    "$SLOTS_DIR/$1" "$2"
}

echo "subagent-concurrency-guard self-test"

echo "1. top-level calls fill the cap, then deny:"
rm -rf "$FAKE_HOME"
mkdir -p "$FAKE_HOME"
transcript "$TMP/top-a.jsonl" "Agent:toolu_A={\"subagent_type\":\"general-purpose\"}"
expect allow "1st top-level dispatch" PreToolUse Agent "$TMP/top-a.jsonl"
[[ "$(slot_count)" -eq 1 ]] && {
  PASS=$((PASS + 1))
  echo "  ok: 1 slot held"
} ||
  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: expected 1 slot, got $(slot_count)" >&2
  }

transcript "$TMP/top-b.jsonl" "Agent:toolu_B={\"subagent_type\":\"general-purpose\"}"
expect allow "2nd top-level dispatch" PreToolUse Agent "$TMP/top-b.jsonl"

transcript "$TMP/top-c.jsonl" "Agent:toolu_C={\"subagent_type\":\"general-purpose\"}"
expect allow "3rd top-level dispatch" PreToolUse Agent "$TMP/top-c.jsonl"
[[ "$(slot_count)" -eq 3 ]] && {
  PASS=$((PASS + 1))
  echo "  ok: 3 slots held"
} ||
  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: expected 3 slots, got $(slot_count)" >&2
  }

transcript "$TMP/top-d.jsonl" "Agent:toolu_D={\"subagent_type\":\"general-purpose\"}"
expect deny "4th top-level dispatch over cap" PreToolUse Agent "$TMP/top-d.jsonl"
[[ "$(slot_count)" -eq 3 ]] && {
  PASS=$((PASS + 1))
  echo "  ok: still 3 slots (4th took none)"
} ||
  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: expected 3 slots, got $(slot_count)" >&2
  }

echo
echo "2. PostToolUse releases a slot, freeing room:"
run PostToolUse Agent "$TMP/top-a.jsonl" >/dev/null
[[ "$(slot_count)" -eq 2 ]] && {
  PASS=$((PASS + 1))
  echo "  ok: 2 slots after release"
} ||
  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: expected 2 slots, got $(slot_count)" >&2
  }
expect allow "dispatch after a slot frees up" PreToolUse Agent "$TMP/top-d.jsonl"
[[ "$(slot_count)" -eq 3 ]] && {
  PASS=$((PASS + 1))
  echo "  ok: back to 3 slots"
} ||
  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: expected 3 slots, got $(slot_count)" >&2
  }

echo
echo "3. stale slots (crashed subagent, no PostToolUse) are reaped by TTL:"
age_slot toolu_B 99999999
age_slot toolu_C 99999999
transcript "$TMP/top-e.jsonl" "Agent:toolu_E={\"subagent_type\":\"general-purpose\"}"
expect allow "cap has room once stale slots are reaped" PreToolUse Agent "$TMP/top-e.jsonl"

echo
echo "4. nested dispatch is denied outright, cap or no cap:"
rm -rf "$FAKE_HOME"
mkdir -p "$FAKE_HOME"
mkdir -p "$TMP/session-x/subagents"
transcript "$TMP/session-x/subagents/agent-nested.jsonl" \
  "Agent:toolu_N={\"subagent_type\":\"general-purpose\"}"
expect deny "subagent's own Agent call, 0 slots occupied" PreToolUse Agent \
  "$TMP/session-x/subagents/agent-nested.jsonl"
[[ "$(slot_count)" -eq 0 ]] && {
  PASS=$((PASS + 1))
  echo "  ok: nesting check short-circuits before any slot lookup"
} ||
  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: expected 0 slots, got $(slot_count)" >&2
  }

transcript "$TMP/top-f.jsonl" "Agent:toolu_F={\"subagent_type\":\"general-purpose\"}"
run PreToolUse Agent "$TMP/top-f.jsonl" >/dev/null
run PreToolUse Agent "$TMP/top-f.jsonl" >/dev/null # harmless double-allow of the same id, same slot
expect deny "still denied with slots available" PreToolUse Agent \
  "$TMP/session-x/subagents/agent-nested.jsonl"

echo
echo "5. PostToolUse for a nested call is a no-op, even if its own tool_use id collides with a real held slot:"
transcript "$TMP/session-x/subagents/agent-nested-collide.jsonl" \
  "Agent:toolu_F={\"subagent_type\":\"general-purpose\"}"
before="$(slot_count)"
run PostToolUse Agent "$TMP/session-x/subagents/agent-nested-collide.jsonl" >/dev/null
after="$(slot_count)"
if [[ "$after" == "$before" ]]; then
  PASS=$((PASS + 1))
  echo "  ok: slot count unchanged ($before -> $after), real slot toolu_F survived a colliding nested id"
else
  FAIL=$((FAIL + 1))
  echo "  FAIL: slot count changed ($before -> $after) — nested PostToolUse released a real slot" >&2
fi

echo
echo "6. a parallel top-level batch is serialized correctly by the lock:"
rm -rf "$FAKE_HOME"
mkdir -p "$FAKE_HOME"
transcript "$TMP/race-1.jsonl" "Agent:toolu_R1={\"subagent_type\":\"general-purpose\"}"
transcript "$TMP/race-2.jsonl" "Agent:toolu_R2={\"subagent_type\":\"general-purpose\"}"
transcript "$TMP/race-3.jsonl" "Agent:toolu_R3={\"subagent_type\":\"general-purpose\"}"
transcript "$TMP/race-4.jsonl" "Agent:toolu_R4={\"subagent_type\":\"general-purpose\"}"
run PreToolUse Agent "$TMP/race-1.jsonl" >"$TMP/race-1.out" &
run PreToolUse Agent "$TMP/race-2.jsonl" >"$TMP/race-2.out" &
run PreToolUse Agent "$TMP/race-3.jsonl" >"$TMP/race-3.out" &
run PreToolUse Agent "$TMP/race-4.jsonl" >"$TMP/race-4.out" &
wait
allowed=0
for f in "$TMP"/race-*.out; do
  grep -q '"permissionDecision": "deny"' "$f" || allowed=$((allowed + 1))
done
if [[ "$allowed" -eq 3 && "$(slot_count)" -eq 3 ]]; then
  PASS=$((PASS + 1))
  echo "  ok: exactly 3 of 4 parallel calls allowed, 3 slots held"
else
  FAIL=$((FAIL + 1))
  echo "  FAIL: expected 3 allowed / 3 slots, got $allowed allowed / $(slot_count) slots" >&2
fi

echo
echo "7. fails open on anything it cannot judge:"
rm -rf "$FAKE_HOME"
mkdir -p "$FAKE_HOME"
expect allow "transcript_path missing entirely" PreToolUse Agent ""
expect allow "transcript_path does not exist" PreToolUse Agent "$TMP/does-not-exist.jsonl"
: >"$TMP/empty.jsonl"
expect allow "empty transcript, no matching tool_use block" PreToolUse Agent "$TMP/empty.jsonl"
printf 'not json at all\n{"broken":\n' >"$TMP/malformed.jsonl"
expect allow "malformed transcript" PreToolUse Agent "$TMP/malformed.jsonl"
[[ "$(slot_count)" -eq 0 ]] && {
  PASS=$((PASS + 1))
  echo "  ok: none of the above created a slot"
} ||
  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: expected 0 slots, got $(slot_count)" >&2
  }

echo
echo "8. non-Agent tool calls are untouched:"
transcript "$TMP/read.jsonl" 'Read={"file_path":"/tmp/a.py"}'
expect allow "a Read call" PreToolUse Read "$TMP/read.jsonl"
[[ "$(slot_count)" -eq 0 ]] && {
  PASS=$((PASS + 1))
  echo "  ok: no slot created for a non-Agent tool"
} ||
  {
    FAIL=$((FAIL + 1))
    echo "  FAIL: expected 0 slots, got $(slot_count)" >&2
  }

echo
echo "subagent-concurrency-guard: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
