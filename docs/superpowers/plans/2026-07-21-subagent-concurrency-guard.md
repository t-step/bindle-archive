# Subagent Concurrency Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a new opt-in `PreToolUse`/`PostToolUse` guard,
`subagent-concurrency-guard.py`, that caps concurrent `Agent`-tool dispatch at
3 and denies nested dispatch (a subagent calling `Agent` itself) outright,
with no escape hatch.

**Architecture:** One Python hook script matched on `tool_name == "Agent"` for
both events. Nesting is detected by checking whether `transcript_path`'s
immediate parent directory is named `subagents` (real Claude Code transcript
layout, verified against on-disk data). The concurrency cap is enforced via a
lock-protected directory of slot files under
`~/.claude/bindle/state/subagent-concurrency/slots/`, one file per in-flight
top-level dispatch, named by that call's `tool_use.id` (read from the
transcript tail using the same technique `codegraph-chaining-guard.py`
already uses). Wired into the existing `bin/install-claude-hooks.sh`
table-driven installer as a new opt-in `--guard subagent-concurrency`.

**Tech Stack:** Python 3 stdlib only (`json`, `os`, `sys`, `time`, `fcntl`,
`contextlib`), Bash for the hermetic self-test (mirrors
`bin/test-codegraph-chaining-guard.sh`).

## Global Constraints

- Full design rationale lives in
  `docs/superpowers/specs/2026-07-21-subagent-concurrency-guard-design.md`;
  every task below implements a piece of it. Read it first if anything here
  is unclear about *why*, not just *what*.
- Cap is **3** concurrent top-level dispatches (`MAX_CONCURRENT = 3`).
- Nesting is **forbidden outright**, no escape hatch, no marker.
- Fails **OPEN** on any state I/O failure or unparseable transcript — never
  block dispatch over the guard's own bug.
- No `capabilities.json` or `CHANGELOG.md` changes — verified directly
  against `bin/check-inventory.py` (only `bin/*.sh|*.py` excluding
  `bin/test-*.sh`, and `docs/*.md`, are scanned; `global/hooks/*.py` is
  outside that surface) and `CHANGELOG.md`'s own header (Release
  Please-generated, no hand-maintained section).
- No `bin/test-install-claude-hooks.sh` changes — verified directly: its
  guard-wiring assertions (section 21) iterate `hook_table()` generically,
  with no hardcoded per-guard list.
- Per this session's explicit direction: **no mutation/pressure-test pass**
  this round. Note it as deferred in the PR/issue, not silently dropped.
- `make check` runs the full commit-hook suite (~2 minutes, including every
  `bin/test-*.sh`) — expect it to take a while at each commit.

---

## File Structure

- `global/hooks/subagent-concurrency-guard.py` — **new.** The guard itself:
  nesting check, slot-directory cap enforcement, `PreToolUse`/`PostToolUse`
  dispatch.
- `bin/test-subagent-concurrency-guard.sh` — **new.** Hermetic self-test:
  synthesized transcripts and payloads in a temp dir, `HOME` overridden so
  the guard's real state directory is never touched.
- `bin/install-claude-hooks.sh` — **modified.** Two new `hook_table()` rows,
  `subagent-concurrency` added to `GUARD_SELECTORS` and the usage line.
- `README.md` — **modified.** Add `subagent-concurrency` to the `--guard`
  name list in the "Session continuity" section.

## Task 1: The guard and its self-test

**Files:**
- Create: `global/hooks/subagent-concurrency-guard.py`
- Create: `bin/test-subagent-concurrency-guard.sh`

**Interfaces:**
- Produces: a script invocable as `python3 global/hooks/subagent-concurrency-guard.py`
  reading a JSON `PreToolUse`/`PostToolUse` hook payload on stdin
  (`hook_event_name`, `tool_name`, `transcript_path` keys used; others
  ignored), writing nothing on allow (exit 0) and
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`
  on deny (also exit 0, per existing guard convention — only the JSON body
  signals deny).
- Consumes: nothing from other tasks (this is the first task).

- [ ] **Step 1: Write the self-test file**

Create `bin/test-subagent-concurrency-guard.sh`:

```bash
#!/usr/bin/env bash
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
rm -rf "$FAKE_HOME"; mkdir -p "$FAKE_HOME"
transcript "$TMP/top-a.jsonl" "Agent:toolu_A={\"subagent_type\":\"general-purpose\"}"
expect allow "1st top-level dispatch" PreToolUse Agent "$TMP/top-a.jsonl"
[[ "$(slot_count)" -eq 1 ]] && { PASS=$((PASS + 1)); echo "  ok: 1 slot held"; } \
  || { FAIL=$((FAIL + 1)); echo "  FAIL: expected 1 slot, got $(slot_count)" >&2; }

transcript "$TMP/top-b.jsonl" "Agent:toolu_B={\"subagent_type\":\"general-purpose\"}"
expect allow "2nd top-level dispatch" PreToolUse Agent "$TMP/top-b.jsonl"

transcript "$TMP/top-c.jsonl" "Agent:toolu_C={\"subagent_type\":\"general-purpose\"}"
expect allow "3rd top-level dispatch" PreToolUse Agent "$TMP/top-c.jsonl"
[[ "$(slot_count)" -eq 3 ]] && { PASS=$((PASS + 1)); echo "  ok: 3 slots held"; } \
  || { FAIL=$((FAIL + 1)); echo "  FAIL: expected 3 slots, got $(slot_count)" >&2; }

transcript "$TMP/top-d.jsonl" "Agent:toolu_D={\"subagent_type\":\"general-purpose\"}"
expect deny "4th top-level dispatch over cap" PreToolUse Agent "$TMP/top-d.jsonl"
[[ "$(slot_count)" -eq 3 ]] && { PASS=$((PASS + 1)); echo "  ok: still 3 slots (4th took none)"; } \
  || { FAIL=$((FAIL + 1)); echo "  FAIL: expected 3 slots, got $(slot_count)" >&2; }

echo
echo "2. PostToolUse releases a slot, freeing room:"
run PostToolUse Agent "$TMP/top-a.jsonl" >/dev/null
[[ "$(slot_count)" -eq 2 ]] && { PASS=$((PASS + 1)); echo "  ok: 2 slots after release"; } \
  || { FAIL=$((FAIL + 1)); echo "  FAIL: expected 2 slots, got $(slot_count)" >&2; }
expect allow "dispatch after a slot frees up" PreToolUse Agent "$TMP/top-d.jsonl"
[[ "$(slot_count)" -eq 3 ]] && { PASS=$((PASS + 1)); echo "  ok: back to 3 slots"; } \
  || { FAIL=$((FAIL + 1)); echo "  FAIL: expected 3 slots, got $(slot_count)" >&2; }

echo
echo "3. stale slots (crashed subagent, no PostToolUse) are reaped by TTL:"
age_slot toolu_B 99999999
age_slot toolu_C 99999999
transcript "$TMP/top-e.jsonl" "Agent:toolu_E={\"subagent_type\":\"general-purpose\"}"
expect allow "cap has room once stale slots are reaped" PreToolUse Agent "$TMP/top-e.jsonl"

echo
echo "4. nested dispatch is denied outright, cap or no cap:"
rm -rf "$FAKE_HOME"; mkdir -p "$FAKE_HOME"
mkdir -p "$TMP/session-x/subagents"
transcript "$TMP/session-x/subagents/agent-nested.jsonl" \
  "Agent:toolu_N={\"subagent_type\":\"general-purpose\"}"
expect deny "subagent's own Agent call, 0 slots occupied" PreToolUse Agent \
  "$TMP/session-x/subagents/agent-nested.jsonl"
[[ "$(slot_count)" -eq 0 ]] && { PASS=$((PASS + 1)); echo "  ok: nesting check short-circuits before any slot lookup"; } \
  || { FAIL=$((FAIL + 1)); echo "  FAIL: expected 0 slots, got $(slot_count)" >&2; }

transcript "$TMP/top-f.jsonl" "Agent:toolu_F={\"subagent_type\":\"general-purpose\"}"
run PreToolUse Agent "$TMP/top-f.jsonl" >/dev/null
run PreToolUse Agent "$TMP/top-f.jsonl" >/dev/null  # harmless double-allow of the same id, same slot
expect deny "still denied with slots available" PreToolUse Agent \
  "$TMP/session-x/subagents/agent-nested.jsonl"

echo
echo "5. PostToolUse for a nested call is a no-op:"
run PostToolUse Agent "$TMP/session-x/subagents/agent-nested.jsonl" >/dev/null
echo "  ok: no crash, nothing to release"
PASS=$((PASS + 1))

echo
echo "6. a parallel top-level batch is serialized correctly by the lock:"
rm -rf "$FAKE_HOME"; mkdir -p "$FAKE_HOME"
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
  PASS=$((PASS + 1)); echo "  ok: exactly 3 of 4 parallel calls allowed, 3 slots held"
else
  FAIL=$((FAIL + 1))
  echo "  FAIL: expected 3 allowed / 3 slots, got $allowed allowed / $(slot_count) slots" >&2
fi

echo
echo "7. fails open on anything it cannot judge:"
rm -rf "$FAKE_HOME"; mkdir -p "$FAKE_HOME"
expect allow "transcript_path missing entirely" PreToolUse Agent ""
expect allow "transcript_path does not exist" PreToolUse Agent "$TMP/does-not-exist.jsonl"
: >"$TMP/empty.jsonl"
expect allow "empty transcript, no matching tool_use block" PreToolUse Agent "$TMP/empty.jsonl"
printf 'not json at all\n{"broken":\n' >"$TMP/malformed.jsonl"
expect allow "malformed transcript" PreToolUse Agent "$TMP/malformed.jsonl"
[[ "$(slot_count)" -eq 0 ]] && { PASS=$((PASS + 1)); echo "  ok: none of the above created a slot"; } \
  || { FAIL=$((FAIL + 1)); echo "  FAIL: expected 0 slots, got $(slot_count)" >&2; }

echo
echo "8. non-Agent tool calls are untouched:"
transcript "$TMP/read.jsonl" 'Read={"file_path":"/tmp/a.py"}'
expect allow "a Read call" PreToolUse Read "$TMP/read.jsonl"
[[ "$(slot_count)" -eq 0 ]] && { PASS=$((PASS + 1)); echo "  ok: no slot created for a non-Agent tool"; } \
  || { FAIL=$((FAIL + 1)); echo "  FAIL: expected 0 slots, got $(slot_count)" >&2; }

echo
echo "subagent-concurrency-guard: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
```

- [ ] **Step 2: Make it executable and run it to verify it fails (the guard doesn't exist yet)**

```bash
chmod +x bin/test-subagent-concurrency-guard.sh
bin/test-subagent-concurrency-guard.sh
```

Expected: fails immediately — `python3: can't open file
'.../global/hooks/subagent-concurrency-guard.py': [Errno 2] No such file or
directory`.

- [ ] **Step 3: Write the guard**

Create `global/hooks/subagent-concurrency-guard.py`:

```python
#!/usr/bin/env python3
"""subagent-concurrency-guard.py — Claude Code PreToolUse/PostToolUse hook.

Caps concurrent Agent-tool dispatch at MAX_CONCURRENT and forbids nested
dispatch outright — a subagent's own Agent call is denied unconditionally, so
nesting cannot be used to route around the cap. Verified against real,
on-disk Claude Code transcripts for this repo (2026-07-21): the dispatch tool
is named `Agent`; each subagent gets its own transcript file at
`<session>/subagents/agent-<agentId>.jsonl`, distinct from the top-level
session's own `<session>.jsonl`; and each `tool_use` block carries a stable
`id`, confirmed by cross-referencing a real dispatch call's `tool_use.id`
against the dispatched subagent's own `meta.json.toolUseId`.

Nesting detection: `PreToolUse`/`PostToolUse`'s `transcript_path` always
names the transcript of the *calling* context (the same fact
`codegraph-chaining-guard.py` documents and relies on) — so a call is nested
exactly when `transcript_path`'s immediate parent directory is `subagents`.

Concurrency cap: a lock-protected slot directory under
`~/.claude/bindle/state/subagent-concurrency/slots/`, deliberately outside
`~/.claude/hooks/`, which `bin/install.sh`/`bin/doctor.sh` manage as a
symlink-only destination — runtime state has no business there. One file per
in-flight top-level dispatch, named by that call's `tool_use.id` (read from
the transcript tail, the same technique `codegraph-chaining-guard.py` uses to
find "the previous tool call" — here used to find "this call"). `PreToolUse`
allows and creates a slot if fewer than MAX_CONCURRENT non-stale slots exist;
`PostToolUse` removes the slot it created. A slot older than
BINDLE_SUBAGENT_SLOT_TTL_SECONDS (default 4 hours) is treated as abandoned (a
crashed subagent that never reached `PostToolUse`) and reaped on sight.

No escape hatch. Every other guard here ships a marker override; this one
does not, deliberately — an override would defeat the one thing this guard
was asked to close.

Fails OPEN: any failure to read/write guard state, or to find a matching
tool_use block, allows the call. A false allow costs at most one subagent
over cap; a false deny would silently brick all dispatch for the rest of a
session the first time this new mechanism's state handling hit a bug — the
same asymmetry `codegraph-chaining-guard.py` documents for its own choice.

Wire-up in ~/.claude/settings.json — note the ~/.claude/hooks path, a symlink
bin/install.sh maintains, so moving the checkout leaves a dangling link this
hook's own nonzero exit and bin/doctor.sh both report:
  "hooks": { "PreToolUse": [ { "matcher": "Agent",
    "hooks": [ { "type": "command",
    "command": "python3 ~/.claude/hooks/subagent-concurrency-guard.py",
    "timeout": 10 } ] } ],
    "PostToolUse": [ { "matcher": "Agent",
    "hooks": [ { "type": "command",
    "command": "python3 ~/.claude/hooks/subagent-concurrency-guard.py",
    "timeout": 10 } ] } ] }
Spell the path out with $HOME expanded (no leading ~);
settings.json is JSON, so an unexpanded ~ survives only if the shell that
runs the command expands it — do not rely on that (#312).
Do not wrap the command in `|| true`: for PreToolUse only exit code 2 blocks a
tool call, so a missing hook already fails visibly without blocking anything.

Self-test: bin/test-subagent-concurrency-guard.sh
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import time

MAX_CONCURRENT = 3
DEFAULT_TTL_SECONDS = 4 * 60 * 60
TAIL_BYTES = 256 * 1024
MAX_LINES = 400
DISPATCH_TOOL = "Agent"

STATE_DIR = os.path.expanduser("~/.claude/bindle/state/subagent-concurrency")
SLOTS_DIR = os.path.join(STATE_DIR, "slots")
LOCK_PATH = os.path.join(STATE_DIR, "slots.lock")


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def is_nested(transcript_path: str) -> bool:
    return os.path.basename(os.path.dirname(transcript_path)) == "subagents"


def tail_lines(path: str) -> list[str]:
    """Last MAX_LINES whole lines of the transcript. Returns [] on any problem."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES))
            chunk = handle.read()
    except OSError:
        return []
    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if size > TAIL_BYTES and lines:
        lines = lines[1:]  # first line is a partial record from the seek
    return lines[-MAX_LINES:]


def newest_dispatch_id(lines: list[str]) -> str | None:
    """The id of the newest Agent tool_use block in the transcript, or None."""
    newest: str | None = None
    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != DISPATCH_TOOL:
                continue
            block_id = block.get("id")
            if isinstance(block_id, str):
                newest = block_id
    return newest


@contextlib.contextmanager
def slots_lock():
    os.makedirs(SLOTS_DIR, exist_ok=True)
    with open(LOCK_PATH, "a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def ttl_seconds() -> float:
    raw = os.environ.get("BINDLE_SUBAGENT_SLOT_TTL_SECONDS")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(DEFAULT_TTL_SECONDS)


def live_slot_count() -> int:
    """Non-stale slots, reaping stale ones. Call only while holding the lock."""
    ttl = ttl_seconds()
    now = time.time()
    count = 0
    for name in os.listdir(SLOTS_DIR):
        path = os.path.join(SLOTS_DIR, name)
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age > ttl:
            with contextlib.suppress(OSError):
                os.remove(path)
            continue
        count += 1
    return count


def handle_pre_tool_use(data: dict) -> None:
    transcript = data.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return  # can't judge -> allow

    if is_nested(transcript):
        deny(
            "Subagent-concurrency guard: this call originates from inside a "
            "subagent. Nested Agent dispatch is forbidden outright — the cap "
            "on concurrent subagents is not per level, so nesting cannot be "
            "used to route around it."
        )

    dispatch_id = newest_dispatch_id(tail_lines(transcript))
    if dispatch_id is None:
        return  # can't identify this call -> allow, no slot created

    try:
        with slots_lock():
            if live_slot_count() >= MAX_CONCURRENT:
                deny(
                    f"Subagent-concurrency guard: {MAX_CONCURRENT} subagents "
                    "are already in flight. Wait for one to finish before "
                    "dispatching another."
                )
            slot_path = os.path.join(SLOTS_DIR, dispatch_id)
            with open(slot_path, "w"):
                pass
    except OSError:
        return  # state I/O failed -> allow


def handle_post_tool_use(data: dict) -> None:
    transcript = data.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return
    if is_nested(transcript):
        return  # never held a slot

    dispatch_id = newest_dispatch_id(tail_lines(transcript))
    if dispatch_id is None:
        return

    slot_path = os.path.join(SLOTS_DIR, dispatch_id)
    with contextlib.suppress(OSError):
        os.remove(slot_path)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — never break the session over the guard
        return
    if not isinstance(data, dict):
        return
    if (data.get("tool_name") or "") != DISPATCH_TOOL:
        return

    event = data.get("hook_event_name")
    if event == "PreToolUse":
        handle_pre_tool_use(data)
    elif event == "PostToolUse":
        handle_post_tool_use(data)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the self-test, verify it passes**

```bash
bin/test-subagent-concurrency-guard.sh
```

Expected: `subagent-concurrency-guard: 24 passed, 0 failed` (exact count may
vary by a couple depending on final step bookkeeping — the hard requirement
is `0 failed` and every `ok:` line present, no `FAIL:` lines).

If step 6 (the parallel-batch race) is flaky in CI (background job scheduling
timing), re-run it standalone a few times:

```bash
for i in 1 2 3; do bin/test-subagent-concurrency-guard.sh | tail -5; done
```

All three runs must report `0 failed`. If it flakes, the lock isn't actually
serializing — that's a real bug in `slots_lock()`, not a test to loosen.

- [ ] **Step 5: Commit**

```bash
git add global/hooks/subagent-concurrency-guard.py bin/test-subagent-concurrency-guard.sh
git commit -m "feat(#<issue>): add the subagent-concurrency guard

Caps concurrent Agent-tool dispatch at 3 and denies nested dispatch
outright, so a subagent cannot route around the cap by dispatching
its own subagents. Not yet wired into bin/install-claude-hooks.sh —
next commit."
```

(Replace `#<issue>` with the real issue number once Task 3 files it — if
this task lands before the issue exists yet, use a plain `feat:` subject
without the issue reference and let the PR body carry the `Resolves #N`
link instead.)

## Task 2: Wire the guard into the installer

**Files:**
- Modify: `bin/install-claude-hooks.sh` — `hook_table()` function, `GUARD_SELECTORS` variable, `usage_error()`'s printed `SELECTORS` line.

**Interfaces:**
- Consumes: `global/hooks/subagent-concurrency-guard.py` (Task 1's output),
  by filename only — this task never edits that file.
- Produces: `bin/install-claude-hooks.sh install --guard subagent-concurrency [--apply]` wires both hook rows.

- [ ] **Step 1: Add the two new hook_table rows**

In `bin/install-claude-hooks.sh`, find the `hook_table()` function:

```bash
hook_table() {
  cat <<'TABLE'
session;session-start-context.py;SessionStart;startup|resume
session;session-end-breadcrumb.py;SessionEnd;
nested-notes;nested-notes-guard.py;PreToolUse;Bash|mcp__.*github.*
label-hygiene;label-hygiene-guard.py;PreToolUse;Bash
codegraph;codegraph-chaining-guard.py;PreToolUse;Bash|mcp__.*codegraph.*
git-push-merged;git-push-merged-branch-guard.py;PreToolUse;Bash
TABLE
}
```

Change it to:

```bash
hook_table() {
  cat <<'TABLE'
session;session-start-context.py;SessionStart;startup|resume
session;session-end-breadcrumb.py;SessionEnd;
nested-notes;nested-notes-guard.py;PreToolUse;Bash|mcp__.*github.*
label-hygiene;label-hygiene-guard.py;PreToolUse;Bash
codegraph;codegraph-chaining-guard.py;PreToolUse;Bash|mcp__.*codegraph.*
git-push-merged;git-push-merged-branch-guard.py;PreToolUse;Bash
subagent-concurrency;subagent-concurrency-guard.py;PreToolUse;Agent
subagent-concurrency;subagent-concurrency-guard.py;PostToolUse;Agent
TABLE
}
```

- [ ] **Step 2: Add the selector to `GUARD_SELECTORS` and the usage strings**

Find:

```bash
GUARD_SELECTORS="nested-notes label-hygiene codegraph git-push-merged"
```

Change to:

```bash
GUARD_SELECTORS="nested-notes label-hygiene codegraph git-push-merged subagent-concurrency"
```

Find (in `usage_error()`):

```bash
  echo "       SELECTORS: --session | --guard <nested-notes|label-hygiene|codegraph|git-push-merged> (repeatable); default --session" >&2
```

Change to:

```bash
  echo "       SELECTORS: --session | --guard <nested-notes|label-hygiene|codegraph|git-push-merged|subagent-concurrency> (repeatable); default --session" >&2
```

- [ ] **Step 3: Run the existing installer self-test to verify nothing broke, and that it now covers the new guard generically**

```bash
bin/test-install-claude-hooks.sh
```

Expected: `passed <N>, failed 0`, where `<N>` is higher than before this
change — section 21 ("the hook table is the ONE declared place a matcher
lives") now iterates two additional rows for `subagent-concurrency-guard.py`
and checks its docstring for `"hooks": {`, `"matcher": "Agent"`,
`"PreToolUse": [`, and `"PostToolUse": [` — all of which Task 1's docstring
already contains. If this fails, the docstring's wire-up JSON block is
missing one of those exact substrings; fix the docstring, not the test.

- [ ] **Step 4: Manual smoke check of the CLI surface**

```bash
bin/install-claude-hooks.sh status
```

Expected: a `subagent-concurrency-guard.py PreToolUse  not wired  →
bin/install-claude-hooks.sh install --guard subagent-concurrency` line (and
likewise for `PostToolUse`) among the output, alongside the existing guards.

```bash
bin/install-claude-hooks.sh install --guard subagent-concurrency --home /tmp/bindle-smoke-home
```

Expected: a preview diff showing both new `PreToolUse`/`PostToolUse` entries
being added to a fresh `/tmp/bindle-smoke-home/settings.json`, ending in "no
changes written (preview)". Clean up: `rm -rf /tmp/bindle-smoke-home`.

- [ ] **Step 5: Commit**

```bash
git add bin/install-claude-hooks.sh
git commit -m "feat: wire the subagent-concurrency guard into the installer

Adds --guard subagent-concurrency, opt-in like every other guard here.
bin/test-install-claude-hooks.sh needed no changes — its assertions are
table-driven and now cover the new rows automatically."
```

## Task 3: Docs, full check, and shipping

**Files:**
- Modify: `README.md` — the `--guard` name list line.

**Interfaces:**
- Consumes: nothing new — this is documentation only.
- Produces: nothing consumed by a later task (final task in this plan).

- [ ] **Step 1: Update the README's guard name list**

Find, in `README.md` (the "Session continuity" section, opt-in hooks
paragraph):

```
The same command wires the `PreToolUse` guards, one at a time and only when
named — `install --guard nested-notes|label-hygiene|codegraph|git-push-merged`. A bare
```

Change to:

```
The same command wires the `PreToolUse` guards, one at a time and only when
named — `install --guard nested-notes|label-hygiene|codegraph|git-push-merged|subagent-concurrency`. A bare
```

- [ ] **Step 2: Run the full check suite**

```bash
make check
```

Expected: every section reports `Passed` (including "Bindle content
(frontmatter/name/links/version)" and "test suites (discovered
bin/test-*.sh)"). This is the same gate the commit hook already runs, so a
green `make check` here means the next commit's hook will also be green —
run it standalone first since it takes ~2 minutes and you don't want that
surprise mid-commit.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: list subagent-concurrency in the guard install line"
```

- [ ] **Step 4: File the tracking issue and open the PR**

Not a code step — this is the shipping step, per this session's earlier
agreement (issue lands with the PR, milestone v0.10, no mutation/pressure
test this round — note that explicitly as deferred in the issue body, not
silently). Use `superpowers:finishing-a-development-branch` /
`fork-pr-flow` conventions already established for this repo. Do not push or
open the PR without the user's go-ahead per this session's standing
instructions on push/PR actions — confirm before executing this step if that
hasn't already been explicitly granted.

## Self-Review

**Spec coverage:** every section of
`docs/superpowers/specs/2026-07-21-subagent-concurrency-guard-design.md` maps
to a task here — nesting detection and cap enforcement (Task 1), no escape
hatch (Task 1, no marker code path exists at all), installer wiring (Task 2),
docs (Task 3). The spec's Testing section's cases are all present in Task 1's
self-test, minus the explicitly-deferred mutation pass.

**Placeholder scan:** no TBD/TODO; every step has complete, runnable code or
an exact command with expected output.

**Type consistency:** `is_nested(transcript_path: str) -> bool`,
`tail_lines(path: str) -> list[str]`, and
`newest_dispatch_id(lines: list[str]) -> str | None` are defined once in Task
1 and used with the same names and signatures throughout the same file — no
other task redefines or renames them.
