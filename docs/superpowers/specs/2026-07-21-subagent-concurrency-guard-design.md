# Subagent concurrency guard — design

**Status:** proposed
**Date:** 2026-07-21

## Problem

Nothing in Claude Code or in this repo currently caps how many subagents can be
in flight at once. A session can fan out an unbounded number of `Agent`-tool
dispatches (parallel batches, repeated sequential dispatch, or a subagent
dispatching its own subagents) with no mechanical ceiling. The user asked for a
hard cap of 3 concurrent subagents, explicitly including closing the obvious
workaround: a dispatched subagent itself dispatching further subagents to
route around a cap enforced only against the top level.

This is not hypothetical. Read-only inspection of this machine's own local
transcripts (`~/.claude/projects/-Users-thomasestep-Developer-bindle/`, never
modified, no hook wired to capture anything new) found a real, already-shipped
case of a subagent dispatching a nested `Agent` call
(`subagent_type: "fork"`) from inside its own transcript file. The workaround
this design closes already happens today.

Requested and confirmed (three prior questions, all answered with the
recommended option):

1. Ship as a new Bindle-owned `PreToolUse`/`PostToolUse` guard, same family as
   `codegraph-chaining-guard.py`, `nested-notes-guard.py`,
   `label-hygiene-guard.py`, `git-push-merged-branch-guard.py` — opt-in via
   `bin/install-claude-hooks.sh --guard subagent-concurrency`.
2. The cap is **global**, not per-transcript: 3 in flight total, top-level and
   nested combined, not "3 per level."
3. Nesting is **forbidden outright** — a subagent-originated dispatch call is
   denied unconditionally, regardless of how many slots are free. It is not
   folded into the same counter as an allowed case; it never reaches the
   counter check at all.

## What the guard enforces

On every dispatch-tool call (`PreToolUse`):

- **If this call originates from inside a subagent → deny, always.** No
  escape hatch, no marker. This is deliberate and matches the explicit ask:
  the cap must not be routable around by nesting, so nesting itself is the
  thing that is blocked, not just over-cap nesting.
- **Else (top-level call) → allow only if fewer than 3 top-level dispatches
  are currently in flight; otherwise deny.**

On the matching `PostToolUse` for an allowed top-level call, the guard
releases the slot it took.

### Why deny nesting outright instead of counting it against the same cap

The alternative (allow nesting, count it against the global-3) was on the
table and rejected in favor of the simpler rule, because:

- It closes the workaround completely rather than partially — there is no
  configuration of nested calls that can ever exceed, or even reach, the cap
  via nesting, because none are permitted.
- It removes an entire class of accounting bugs: nested calls would still need
  the same slot bookkeeping as top-level ones, but arriving from a different
  transcript, at arbitrary depth, with no cheap way to attribute a slot release
  back to the right dispatcher if a subagent chain dies mid-flight.
- It matches the user's own framing of the ask ("don't want subagents to work
  around this by nesting") as a flat prohibition, not a relaxed accounting
  rule.

### No escape hatch

Every other guard in this repo ships a marker-based override
(`cg-chain-ok`, `nested-notes-exempt`, the label-hygiene issue-keyed hatch).
This one does not. An override defeats the specific thing the user asked to
close. If a real need to exceed 3, or to nest, shows up later, that is a
follow-up decision to make deliberately — not a default this design should
pre-empt.

## Mechanism

### Detecting "is this call nested"

Verified directly against real, on-disk transcript data for this repo (not
guessed, not inferred from the minified CLI bundle): every session directory
under `~/.claude/projects/<project>/<session-uuid>/` that has ever dispatched
a subagent has a `subagents/` child directory holding one
`agent-<agentId>.jsonl` (that subagent's own transcript, its records tagged
`"isSidechain": true`) plus a paired `agent-<agentId>.meta.json`
(`agentType`, `isFork`, `description`, `toolUseId`, `spawnDepth`) per
dispatched subagent. `codegraph-chaining-guard.py` already relies on, and
documents, the fact that `PreToolUse`'s `transcript_path` field always points
to the transcript of the *calling* context — the top-level session's own
`<session-uuid>.jsonl` for a top-level call, a subagent's own
`subagents/agent-<id>.jsonl` for a call made from inside that subagent.

So nesting detection is exactly: **is the immediate parent directory of
`transcript_path` named `subagents`?**

```python
import os
def is_nested(transcript_path: str) -> bool:
    return os.path.basename(os.path.dirname(transcript_path)) == "subagents"
```

No state file, no bootstrap race, no per-session recording, no mid-session
misclassification window — the answer is fully determined by the one
`transcript_path` value every `PreToolUse`/`PostToolUse` call already carries,
with no dependency on when the guard happened to get wired.

### Enforcing the cap

A lock-protected slot directory under
`~/.claude/bindle/state/subagent-concurrency/slots/` — deliberately **not**
under `~/.claude/hooks/`, which `bin/install.sh`/`bin/doctor.sh` manage as a
symlink-only destination; runtime state has no business there. One small file
per in-flight top-level dispatch. `PreToolUse`, holding a lock on a sibling
`slots.lock`, counts non-stale slot files; allows and creates a new slot file
if the count is below 3, denies otherwise. `PostToolUse` removes the slot file
for the call it corresponds to.

**Stale-slot reaping:** a slot whose file is older than a TTL (default 4
hours, overridable via `BINDLE_SUBAGENT_SLOT_TTL_SECONDS` — generous because
some subagents legitimately run long, but bounded so a crashed subagent that
never reaches `PostToolUse` cannot permanently shrink the cap) is treated as
free and removed when encountered during a count.

### Correlating `PreToolUse` and `PostToolUse` for the same call

Verified directly against real transcript data: each `tool_use` block already
carries its own stable `id` (e.g. `toolu_01794DzDwtpWtTKySnUunKD1`) in the
transcript JSONL itself — confirmed by cross-referencing a real dispatch
call's `tool_use.id` in the parent transcript against the dispatched
subagent's own `meta.json.toolUseId`, which matched exactly. This is the same
transcript the guard already reads for the nesting check, and reading it for
the correlation id reuses `codegraph-chaining-guard.py`'s established
technique (read the tail, find the newest matching `tool_use` block) rather
than depending on any undocumented `PreToolUse`/`PostToolUse` payload field:

- **`PreToolUse` (top-level, allowed):** find the newest `tool_use` block in
  the transcript tail with `name == "Agent"` — per
  `codegraph-chaining-guard.py`'s documented reasoning, `PreToolUse` fires
  right after the assistant message carrying this exact call is written, so
  that newest block *is* this call. Use its `id` as the slot filename.
- **`PostToolUse` (top-level):** same lookup, same transcript, same helper —
  by the time `PostToolUse` fires the block is still the newest `Agent`
  `tool_use` entry for this call. Remove the slot file for that `id` if
  present; a missing slot (already reaped by TTL, or never created because
  the cap check failed open) is a no-op, not an error.
- If no matching `tool_use` block is found in either event (fails open): no
  slot is created (`PreToolUse`) or nothing is removed (`PostToolUse`) — the
  failure direction is always toward under-counting, never toward a stuck
  slot.

## Failure posture: fails OPEN

Any failure to read or write guard state — state directory uncreatable, lock
unavailable, `transcript_path` missing from the payload, or the transcript
itself unreadable/unparseable/lacking a matching `tool_use` block — **allows**
the call rather than denying it.

This is a new mechanism with no track record. The asymmetry: a false allow
here costs at most one extra in-flight subagent beyond the intended cap of 3,
or one nested call that should have been denied — self-limiting, purely
internal, no external or irreversible artifact. A false deny, on the other
hand, would silently brick all subagent dispatch for the rest of a session the
first time the guard's own state handling hit a bug or an environment quirk
(permissions, disk full, an unexpected payload shape) — a much worse outcome
than the cap being briefly ineffective. Same reasoning `codegraph-chaining-guard.py`
gives for its own fail-open choice; the opposite of `nested-notes-guard.py`'s
fail-closed MCP path, which guards against an unreviewable external artifact
that has no analog here.

Per `#264`/`#312` convention: the wire-up carries no `|| true`; a missing or
broken hook script already fails visibly via a nonzero exit without wedging
anything, so nothing should suppress that.

## Files

| file | change |
|---|---|
| `global/hooks/subagent-concurrency-guard.py` | new — the guard |
| `bin/test-subagent-concurrency-guard.sh` | new — hermetic self-test |
| `bin/install-claude-hooks.sh` | new `hook_table` rows (`PreToolUse` + `PostToolUse`), `subagent-concurrency` added to `GUARD_SELECTORS` and the printed usage line |
| `README.md` | add `subagent-concurrency` to the `--guard` name list |

`bin/test-install-claude-hooks.sh` needs **no change** — verified by reading it: its guard-wiring assertions (section 21) iterate `hook_table()` generically and check each script's own docstring, with no hardcoded per-guard list or count anywhere in the file.
| `CHANGELOG.md` | entry marked **draft** until pressure-tested (RED → GREEN → REFACTOR), per this repo's skill-writing rule |

## Testing

`bin/test-subagent-concurrency-guard.sh`, hermetic — synthesized `PreToolUse`/
`PostToolUse` payloads and a synthesized state directory in a temp dir, never
a real transcript or a real `~/.claude` tree. Cases:

- top-level call (`transcript_path` not under a `subagents/` dir), 0 slots occupied → allow, slot created named by the call's `tool_use.id`
- top-level call, 1–2 slots occupied → allow, slot created
- top-level call, 3 slots occupied → **deny**
- top-level call, 3 slots occupied but one is older than the TTL → allow (stale slot reaped)
- nested call (`transcript_path`'s parent dir is `subagents`), 0 slots occupied → **deny**
- nested call, would-be-available slots → **deny** (nesting check short-circuits before the count is even consulted; no slot lookup happens)
- `PostToolUse` for a call that took a slot → slot file removed
- `PostToolUse` for a nested call → no-op (never held a slot)
- two simultaneous top-level `PreToolUse` calls (a parallel dispatch batch) racing on the same slot directory → lock serializes them, both counted correctly, no double-allow past 3
- state directory uncreatable / lock unavailable / `transcript_path` missing or unreadable / no matching `tool_use` block found → allow (fails open)
- non-`Agent` tool call → untouched, no-op

**Mutation pass deferred by explicit decision** (not this round): the repo
convention for a new gate is to invert the cap comparison and the nesting
check independently and confirm each inversion flips the corresponding deny
cases to allow. Skipped here at the user's direction; the CHANGELOG entry and
the tracking issue both mark this guard as an unverified draft until that
pass runs, per this repo's skill-writing rule of not describing a draft as
finished.

## Open, deferred

- Whether 3 is the right steady-state number, and whether a future need for an
  explicit, deliberate override (cap or nesting) ever arises, is left for a
  later decision if it comes up — not pre-solved with an escape hatch now.
- The transcript-directory layout this design depends on
  (`<session>/subagents/agent-<id>.jsonl`) is observed, real, on-disk behavior
  of the installed Claude Code CLI, not a documented/versioned public
  contract. If a future CLI version changes that layout, the guard fails open
  (no matching transcript shape → allow), so a layout change degrades to "cap
  temporarily ineffective," not "subagent dispatch silently broken."
