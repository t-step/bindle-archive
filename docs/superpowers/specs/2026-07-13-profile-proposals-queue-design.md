# Profile proposals queue — design

## Problem

`/session-end` step 6 currently says: "If the session produced real
profile-worthy facts... suggest updating the profile — one line, user's
call." That suggestion lives only in that session's prose and is never
tracked. A survey of the notes home (2026-07-12) found this is a real,
recurring failure: nearly every Bindle session ends with 1-2 proposed
`profile.md` lines explicitly marked "not yet written — user's call," and
they are not picked up in later sessions. Roughly 8 sessions' worth had
piled up, unaddressed.

## Goal

Every profile-worthy fact identified at session end gets a real decision —
**Add**, **Defer**, or **Reject** — and that decision persists:

- **Add** writes the line into `profile.md` now.
- **Defer** is a no-op: the proposal carries forward and resurfaces at the
  next interactive `/session-end`, instead of silently disappearing.
- **Reject** discards it permanently — it will not be proposed again.

## New artifact: `profile-proposals.md`

A new file in the notes home, alongside the existing per-project artifacts:

```
~/.bindle/projects/<project>/
  profile.md                 # existing — durable, curated facts
  profile-proposals.md       # new — pending Add/Defer/Reject queue
  sessions/YYYY-MM-DD-<slug>.md
  handoffs/YYYY-MM-DD-<slug>.md
```

One list item per pending proposal:

```markdown
# Pending profile.md proposals — <project>

Awaiting a decision (Add / Defer / Reject) at the next interactive
/session-end. Deferred items stay here; rejected items are removed; added
items move into profile.md and are removed from here.

- [2026-07-12 product-boundary-retriage] (recurring instructions) Re-triage
  product-boundary.md's backlog after any issue-state-changing PR.
```

Each entry carries:
- **origin** — date + session slug that proposed it (traceability, matches
  the `sessions/YYYY-MM-DD-<slug>.md` naming already in use).
- **target section** — which `profile.md` section it belongs in (project /
  common commands / validation gates / important docs / safety notes /
  recurring instructions / context locations), decided at proposal time so
  an approved item files itself correctly without re-deriving that later.
- **proposed line text** — the exact line as it would land in `profile.md`.

The file does not exist until the first proposal is queued. It is deleted
(or left as just the header) once the queue drains to zero.

## `/session-end` flow change

Replaces the current step 6 ("suggest updating the profile — one line,
user's call") with:

1. **Load** — read `profile-proposals.md` for this project, if it exists.
   These are carried-over items from past sessions (previously deferred).
2. **Identify new** — from this session's actual work, apply the same bar
   as today (a durable gate, safety note, recurring instruction, etc.) to
   spot any new profile-worthy facts. Tag each with today's date, this
   session's slug, and its target `profile.md` section. Add to the
   in-memory pending list — nothing is written yet.
3. **Nothing pending** (no carryover, nothing new) — skip silently, move on
   to the rest of `/session-end`.
4. **Interactive turn** (a live user will see this reply and can respond
   now) — present the full combined pending list via `AskUserQuestion`, one
   question per item, options Add/Defer/Reject. Batch ≤4 questions per
   call; issue multiple calls if there are more than 4 pending items. Then
   apply the answers:
   - **Add** → append the line to the correct section of `profile.md`
     (creating it via `/project-profile`'s conventions first if it doesn't
     exist yet); drop the item from the pending list.
   - **Defer** → leave it in the pending list, untouched.
   - **Reject** → drop it from the pending list permanently.
   Rewrite `profile-proposals.md` with whatever remains pending, or delete
   it if the queue is now empty.
5. **Unattended/scheduled run** (no one available to respond right now) —
   skip the interactive ask entirely. Just append this session's new
   proposals (from step 2) to `profile-proposals.md` as pending, and
   continue. An unattended run never blocks waiting on an answer, and never
   writes to `profile.md` on its own (this preserves the existing "no
   automatic promotion" rule in `docs/iterative-improvement.md`).
6. The session note's **candidate workflow improvements** section records
   the actual outcome per item this run touched (e.g. "profile: added 'X'
   to safety notes", "profile: still pending", "profile: rejected — Y"),
   rather than the old generic one-line suggestion.

## Data flow

```
new fact found this session
        │
        ▼
  in-memory pending item ──┐
                           ├─▶ merged with profile-proposals.md carryover
carried-over pending items ┘
        │
        ├── interactive: present all → decision ──┬─ Add    → profile.md
        │                                          ├─ Defer  → profile-proposals.md (stays)
        │                                          └─ Reject → discarded
        │
        └── unattended: append new items to profile-proposals.md, no ask, no profile.md write
```

## Edge cases

- **`profile-proposals.md` missing** — treat as an empty queue; create on
  first write.
- **`profile.md` missing** — Add triggers `/project-profile`'s existing
  create path.
- **>4 pending items** — multiple `AskUserQuestion` calls.
- **Duplicate proposal** — light dedupe against existing pending entries by
  meaning, not just exact text match; don't re-queue the same fact twice.
- **Ambiguous/partial answer to the batch** — don't guess; re-ask only the
  unclear items.

## Testing

Add a new claim to `skills/session-continuity/PRESSURE-TESTS.md`, following
the file's existing RED → GREEN → REFACTOR method (fresh subagents, fixture
notes home, filesystem as ground truth, 5 reps per variant):

**Claim** — a deferred profile proposal persists and resurfaces at the next
`/session-end` run, rather than being mentioned once and lost.

- RED: no queue mechanism — proposal appears in one session note's prose,
  never appears again in a later session-end run.
- GREEN: real `/session-end` + this design — proposal is written to
  `profile-proposals.md`, and a second `/session-end` run against the same
  fixture re-presents it for a decision.

Per explicit instruction from this session: **pause before running the
pressure tests and notify the user** — do not proceed into that stage
automatically once the implementation is written. When that stage starts,
follow the new repo-wide convention in `CONTRIBUTING.md` (added alongside
this spec): ask how to run the reps — sequential (recommended), parallel, or
defer and file a `type: chore` / `status: triage` issue — rather than just
launching them.
