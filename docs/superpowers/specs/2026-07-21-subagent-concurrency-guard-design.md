# Subagent concurrency guard — design

**Status:** proposed
**Date:** 2026-07-21

## Problem

Nothing in Claude Code or in this repo currently caps how many subagents can be
in flight at once. A session can fan out an unbounded number of `Task`-tool
dispatches (parallel batches, repeated sequential dispatch, or a subagent
dispatching its own subagents) with no mechanical ceiling. The user asked for a
hard cap of 3 concurrent subagents, explicitly including closing the obvious
workaround: a dispatched subagent itself dispatching further subagents to
route around a cap enforced only against the top level.

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

No hook payload field is assumed without verification (see Phase 0 below).
The chosen detection does not depend on any undocumented field:

**A session's first-ever dispatch-tool call is always top-level**, because a
subagent cannot exist before something has dispatched it. So: the guard reads
`session_id` and `transcript_path` from the `PreToolUse` payload. On the first
dispatch call it has seen for that `session_id`, it records that call's
`transcript_path` as the session's root transcript (atomic create via
`O_CREAT | O_EXCL`, so a parallel top-level batch — several dispatch calls
launched in one turn — races safely: all of them share the same top-level
`transcript_path`, so whichever process wins the create, the others read back
the same value and agree). Every later dispatch call in that session is
top-level if its own `transcript_path` matches the recorded root, and nested
otherwise — a subagent's dispatch calls are recorded in a transcript file of
their own, per the existing observation in `codegraph-chaining-guard.py` that
"it works unchanged inside a subagent because each subagent has its own
transcript."

**Known limitation, accepted:** if the guard is wired for the first time in
the middle of an already-running session that has subagents active, the first
dispatch call the guard observes may itself be nested, and would be
misclassified as root. Narrow window (guard install mid-flight with a live
subagent chain), not solved here.

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

Root-transcript records
(`~/.claude/bindle/state/subagent-concurrency/roots/<session_id>`) are tiny and
not TTL-reaped; a session's root does not change for the life of that session.

### Correlating `PreToolUse` and `PostToolUse` for the same call

Needs a stable identifier present in both events to know which slot a given
`PostToolUse` should release. Existence and name of this field is unconfirmed
— this is the second thing Phase 0 verifies. Fallback if no such field exists:
match on `(session_id, transcript_path, tool_input)` tuple, accepting that two
truly identical concurrent calls in the same batch would be ambiguous (rare —
identical dispatch prompts launched in parallel — and the failure mode is
merely releasing the wrong one of two otherwise-interchangeable slots, not a
miscount).

## Phase 0 — empirical verification (before writing the real guard)

A throwaway capture hook, wired broadly, dumps raw `PreToolUse`/`PostToolUse`
JSON to a scratch file for: one top-level dispatch call, and one nested
dispatch call (a dispatched subagent itself dispatching another). Confirms,
before any real guard code is written:

1. The exact `tool_name` value for a dispatch call (candidate: `Task`; this
   session's own tool listing calls it "Agent", which may be a display-layer
   rename over the same internal tool name — not assumed either way).
2. A stable per-call correlation id present in both `PreToolUse` and
   `PostToolUse` for the same dispatch (or confirmation that none exists, in
   which case the fallback correlation above is used).
3. That `transcript_path` really does differ between a top-level call and a
   nested one, as the nesting-detection mechanism assumes.

Findings get folded into the real guard and its docstring, in the same
evidence-cited style as `codegraph-chaining-guard.py`. The capture hook is
deleted once its findings are recorded — it is a spike, not a shipped file.

## Failure posture: fails OPEN

Any failure to read or write guard state — state directory uncreatable,
lock unavailable, a record unreadable or unparseable, `session_id` or
`transcript_path` missing from the payload — **allows** the call rather than
denying it.

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
| `bin/install-claude-hooks.sh` | new `hook_table` rows (`PreToolUse` + `PostToolUse`), new `--guard subagent-concurrency` selector, usage strings |
| `bin/test-install-claude-hooks.sh` | extend matcher/wiring assertions to cover the new guard |
| `capabilities.json` | record the capability, `make check` reconciles |
| `README.md` | add `subagent-concurrency` to the `--guard` name list |
| `CHANGELOG.md` | entry marked **draft** until pressure-tested (RED → GREEN → REFACTOR), per this repo's skill-writing rule |

## Testing

`bin/test-subagent-concurrency-guard.sh`, hermetic — synthesized `PreToolUse`/
`PostToolUse` payloads and a synthesized state directory in a temp dir, never
a real transcript or a real `~/.claude` tree. Cases:

- first dispatch call in a session, 0 slots occupied → allow, root recorded, slot created
- top-level call, 1–2 slots occupied → allow, slot created
- top-level call, 3 slots occupied → **deny**
- top-level call, 3 slots occupied but one is older than the TTL → allow (stale slot reaped)
- nested call (transcript differs from recorded root), 0 slots occupied → **deny**
- nested call, would-be-available slots → **deny** (nesting check short-circuits before the count is even consulted)
- `PostToolUse` for a call that took a slot → slot file removed
- two simultaneous top-level `PreToolUse` calls racing to create the root record → both agree on the same root, no crash, no double-count
- state directory uncreatable / lock unavailable / payload missing `session_id` or `transcript_path` → allow (fails open)
- non-dispatch tool call → untouched, no-op

**Mutation pass**, per the repo rule that a new gate must be proven failable:
invert the cap comparison and the nesting check independently, confirm each
inversion flips the corresponding deny cases to allow (and vice versa).

## Open, deferred

- The two Phase 0 unknowns (exact `tool_name`, correlation id availability)
  are deliberately left open here and resolved empirically before
  implementation, not guessed.
- Whether 3 is the right steady-state number, and whether a future need for an
  explicit, deliberate override (cap or nesting) ever arises, is left for a
  later decision if it comes up — not pre-solved with an escape hatch now.
- The mid-session wire-up misclassification window (guard installed while a
  subagent chain is already live) is accepted, not solved.
