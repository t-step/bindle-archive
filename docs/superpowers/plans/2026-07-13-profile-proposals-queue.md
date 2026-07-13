# Profile Proposals Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every profile-worthy fact identified at `/session-end` get a real, persistent Add/Defer/Reject decision instead of a one-off suggestion that's forgotten by the next session.

**Architecture:** A new per-project notes-home file, `profile-proposals.md`, holds pending proposals across sessions. `/session-end` loads it, adds any new proposals this session surfaced, and — on a live interactive turn — resolves the whole batch via the `AskUserQuestion` tool before writing the session note, so the note's "candidate workflow improvements" section can record the actual outcome. Unattended runs never ask; they just append and move on.

**Tech Stack:** Plain Markdown (Bindle's notes-home convention) + Claude-native command/skill prompt files (`commands/session-end.md`, `skills/session-continuity/SKILL.md`). No code, no new scripts.

## Global Constraints

- Branch-and-PR: all work lands on `feature/profile-proposals-queue` (already created off `main`; two commits already on it — `5e27d47` design spec, `f02c650` the CONTRIBUTING.md pressure-test run-mode convention). Never commit to `main`.
- `make check` must pass before every commit (pre-commit hook enforces branch discipline + structural checks: frontmatter, links, capability inventory). Never `--no-verify`.
- Notes-home resolution: `$BINDLE_NOTES_DIR` (deprecated `$CLAUDE_KIT_NOTES_DIR` alias) else `~/.bindle`; `projects/<project>/` where `<project>` is the repo's kebab-cased dirname per `bin/slugify.sh`.
- `profile.md` has exactly these 7 sections (verbatim names, from `commands/project-profile.md`): project, common commands, validation gates, important docs, safety notes, recurring instructions, context locations.
- `AskUserQuestion` batches at most 4 questions per call; issue further calls for remaining items.
- No automatic promotion: `profile.md` is written only after an explicit per-item **Add** answer on a live interactive turn. An unattended run never writes to `profile.md`.
- Per explicit instruction from the design session: **pause before running any pressure-test reps and notify the user** — this plan stops short of executing reps.
- Per the already-committed `CONTRIBUTING.md` convention (`f02c650`): before running pressure-test reps interactively (a *future*, separate step, not part of this plan), ask sequential (recommended) / parallel / defer-and-file-a-`type: chore`/`status: triage`-issue.

---

### Task 1: Document the profile-proposals queue in the session-continuity skill

**Files:**
- Modify: `skills/session-continuity/SKILL.md` (notes-home tree block ~line 22-29, new section after the notes-home bullet list ~line 43, Common mistakes list ~line 105-121, Session note shape ~line 90-103)

**Interfaces:**
- Produces: the exact `profile-proposals.md` entry format `- [<date> <session-slug>] (<profile.md section>) <exact proposed line>`, the file's header/lifecycle prose, and the Add/Defer/Reject semantics — Task 2's command steps reference this verbatim as "session-continuity's Profile proposals queue".

- [ ] **Step 1: Add `profile-proposals.md` to the notes-home tree**

Edit `skills/session-continuity/SKILL.md`, in the fenced tree block under "## The notes home":

Old:
```
  projects/<project>/
    profile.md                        # durable facts: gates, commands, safety notes
    sessions/YYYY-MM-DD-<slug>.md     # one note per session
    handoffs/YYYY-MM-DD-<slug>.md     # paste-ready prompts for future sessions
```

New:
```
  projects/<project>/
    profile.md                        # durable facts: gates, commands, safety notes
    profile-proposals.md              # pending profile.md Add/Defer/Reject queue
    sessions/YYYY-MM-DD-<slug>.md     # one note per session
    handoffs/YYYY-MM-DD-<slug>.md     # paste-ready prompts for future sessions
```

- [ ] **Step 2: Insert the "Profile proposals queue" section**

Edit `skills/session-continuity/SKILL.md`, immediately after the existing notes-home bullet list and before the `## Rules` heading.

Old (the exact boundary text — insert between these two):
```
- Create directories on demand (`mkdir -p`). Plain Markdown only.

## Rules
```

New:
```
- Create directories on demand (`mkdir -p`). Plain Markdown only.

## Profile proposals queue

`profile-proposals.md` holds facts proposed for `profile.md` that don't yet
have a decision. `/session-end` is the only writer: it loads any pending
entries left over from earlier sessions, adds any new profile-worthy facts
this session surfaced, and — on a live interactive turn — asks Add / Defer /
Reject for each one via the `AskUserQuestion` tool (batched at most 4
questions per call). Add moves the line into `profile.md`'s named section and
drops the entry; Defer leaves the entry untouched, to resurface next time;
Reject removes it for good. An unattended run never asks — it just appends
new proposals as pending and moves on, so `profile.md` is never written to
without an explicit per-item answer.

Format — one entry per pending proposal:

```markdown
# Pending profile.md proposals — <project>

Awaiting a decision (Add / Defer / Reject) at the next interactive
/session-end. Deferred items stay here; rejected items are removed; added
items move into profile.md and are removed from here.

- [2026-07-12 product-boundary-retriage] (recurring instructions) Re-triage
  product-boundary.md's backlog after any issue-state-changing PR.
```

Each entry is `- [<date> <session-slug>] (<profile.md section>) <exact
proposed line>` — the section name matches one of `profile.md`'s seven
headings (project, common commands, validation gates, important docs, safety
notes, recurring instructions, context locations). The file doesn't exist
until the first proposal is queued, and is deleted once the queue empties.

## Rules
```

- [ ] **Step 3: Point the session note shape at the new section**

Edit `skills/session-continuity/SKILL.md`, in `## Session note shape`:

Old:
```
candidate workflow improvements: (see Bindle's `docs/iterative-improvement.md`)
```

New:
```
candidate workflow improvements: (see Bindle's `docs/iterative-improvement.md`;
  profile updates specifically: see "Profile proposals queue" above)
```

- [ ] **Step 4: Add a Common mistakes entry**

Edit `skills/session-continuity/SKILL.md`, appending to the `## Common mistakes` list (after its last existing bullet, "Blocking on a missing notes home..."):

Old:
```
- Blocking on a missing notes home — `mkdir -p` and continue; never ask the
  user to create directories.
```

New:
```
- Blocking on a missing notes home — `mkdir -p` and continue; never ask the
  user to create directories.
- Writing a profile-worthy fact straight into `profile.md` without queuing it
  through `profile-proposals.md` first — even an obviously-true fact still
  needs its own Add/Defer/Reject decision on a live turn; the only exception
  is an unattended run, which queues it as pending and does not touch
  `profile.md` at all.
```

- [ ] **Step 5: Verify structure**

Run (from the repo root): `make check`
Expected: `Hygiene checks PASSED` (or equivalent all-green output) — no broken links, valid frontmatter, capability inventory unaffected (this task adds no new repo files).

Re-read the new "Profile proposals queue" section side-by-side with the design spec's Part 1 (`docs/superpowers/specs/2026-07-13-profile-proposals-queue-design.md`) and confirm the fenced format block matches verbatim.

- [ ] **Step 6: Commit**

```bash
git add skills/session-continuity/SKILL.md
git commit -m "feat(session-continuity): document the profile-proposals queue"
```

---

### Task 2: Wire the profile-proposals flow into `/session-end`

**Files:**
- Modify: `commands/session-end.md` (entire `Steps:` section)
- Modify: `CHANGELOG.md` (`[Unreleased]` → `### Changed`)

**Interfaces:**
- Consumes: Task 1's `profile-proposals.md` format and Add/Defer/Reject semantics (session-continuity SKILL.md's "Profile proposals queue" section); `profile.md`'s 7 section names from `commands/project-profile.md`.
- Produces: the new step order (1 resolve paths, 2 reconstruct+slug, 3 label reconciliation, 4 profile proposals, 5 write note, 6 privacy pass) that Task 3's pressure-test claim exercises.

- [ ] **Step 1: Replace the `Steps:` section**

Edit `commands/session-end.md`. Replace everything from `Steps:` through the end of the file.

Old (verbatim, current file):
```
Steps:

1. Read the `session-continuity` skill; resolve the notes home
   (`$BINDLE_NOTES_DIR`, deprecated `$CLAUDE_KIT_NOTES_DIR`, or `~/.bindle`) and
   `projects/<project>/sessions/`; `mkdir -p` as needed.
2. Reconstruct the session honestly from the conversation and git state — what
   was actually done, not what was intended. If tests weren't run, the note
   says "not run", not "passing".
3. Label reconciliation (skip silently if there's no GitHub remote, `gh` is
   unavailable or unauthenticated, or this session touched no issues):
   - Identify issues this session touched — numbers referenced in the branch
     name, commit subjects/bodies (`#123`), or named explicitly in
     conversation.
   - For each, `gh issue view <N> --json state,labels` to see its current
     `status:` label (exact text, space after the colon — see
     `docs/issue-tracking.md` for the taxonomy) and open/closed state.
   - Compare to what the session actually did. If the work is finished,
     propose `gh issue close <N> --comment "<one-line summary>"`. If the
     `status:` label no longer matches reality, propose
     `gh issue edit <N> --remove-label "status: X" --add-label "status: Y"`
     with the exact before/after label text. Skip an issue with no proposed
     change.
   - Present every proposed command as one batch and wait for explicit user
     approval before running any of them — never run a mutating `gh` command
     unapproved.
   - Record what ran (or that nothing needed to change) — it feeds the
     session note's **decisions** section below.
4. Write `sessions/YYYY-MM-DD-<slug>.md` containing:
   - **goal** — what this session set out to do;
   - **branch** and **commits made** (hashes + subjects);
   - **files changed** (paths only);
   - **tests/checks run** and their actual results;
   - **validation status** — green / red / not verified;
   - **decisions** — one line each, with the why (including any label
     reconciliation from step 3);
   - **risks** — what could bite a future session;
   - **deferred** — consciously not done;
   - **candidate workflow improvements** — answer each briefly:
     new reusable skill? existing skill to update? project profile update?
     validation/check to add? privacy rule to add? nothing worth keeping?
   - **next** — the single most useful next prompt.
5. Privacy pass: this note stays in the notes home, so local paths are fine —
   but confirm nothing session-private (transcripts, personal details) was
   left in *repo* files or staged changes. Flag anything you find; don't
   silently fix it.
   - If the user's closing note asks for the summary **in the repo or PR**
     (e.g. "save it as NOTES.md" / "so my teammate sees it"), do not write the
     note above into the repo. Follow the skill's **Repo-bound content**
     recipe: keep the full note in the notes home (step 4), then produce a
     *separate* sanitized summary and run `bin/check-private-info.sh` on it —
     block on the result — before leaving it (unstaged) in the repo.
6. If the session produced real profile-worthy facts (a new gate, a new
   safety rule), suggest updating the profile — one line, user's call.

Reply with the note's full path and the note itself. If the user wants a
paste-ready prompt for the next session, that's `/handoff` — offer it, don't
run it.
```

New:
```
Steps:

1. Read the `session-continuity` skill; resolve the notes home
   (`$BINDLE_NOTES_DIR`, deprecated `$CLAUDE_KIT_NOTES_DIR`, or `~/.bindle`) and
   `projects/<project>/sessions/`; `mkdir -p` as needed.
2. Reconstruct the session honestly from the conversation and git state — what
   was actually done, not what was intended. If tests weren't run, the note
   says "not run", not "passing". Settle today's date and this session's slug
   now (`bin/slugify.sh`, session-continuity's slug rule) — steps 4 and 5 both
   reuse it.
3. Label reconciliation (skip silently if there's no GitHub remote, `gh` is
   unavailable or unauthenticated, or this session touched no issues):
   - Identify issues this session touched — numbers referenced in the branch
     name, commit subjects/bodies (`#123`), or named explicitly in
     conversation.
   - For each, `gh issue view <N> --json state,labels` to see its current
     `status:` label (exact text, space after the colon — see
     `docs/issue-tracking.md` for the taxonomy) and open/closed state.
   - Compare to what the session actually did. If the work is finished,
     propose `gh issue close <N> --comment "<one-line summary>"`. If the
     `status:` label no longer matches reality, propose
     `gh issue edit <N> --remove-label "status: X" --add-label "status: Y"`
     with the exact before/after label text. Skip an issue with no proposed
     change.
   - Present every proposed command as one batch and wait for explicit user
     approval before running any of them — never run a mutating `gh` command
     unapproved.
   - Record what ran (or that nothing needed to change) — it feeds the
     session note's **decisions** section below.
4. Profile proposals — resolve before writing the note, so its outcome lands
   in the note itself. Per session-continuity's **Profile proposals queue**:
   - Read `profile-proposals.md` in `projects/<project>/` (same notes home as
     step 1) if it exists; these are pending entries carried over from
     earlier sessions (previously deferred).
   - From this session's actual work, apply the usual bar (a durable
     validation gate, safety note, recurring instruction — not something
     already in the project's own README/CLAUDE.md) to spot any new
     profile-worthy facts. Tag each with the date/slug from step 2 and the
     `profile.md` section it targets (project, common commands, validation
     gates, important docs, safety notes, recurring instructions, context
     locations). Before adding a new fact to the in-memory list, check it
     against the carried-over pending entries from this same step — if an
     existing entry already covers the same fact (even worded differently),
     don't queue a duplicate. Nothing is written to disk yet.
   - Nothing pending (no carryover, nothing new)? Record "profile: nothing
     pending" and move on to step 5.
   - **Interactive turn** (a live user will see this reply and can respond
     now): present the full combined list via the `AskUserQuestion` tool, one
     question per item, options exactly `Add` / `Defer` / `Reject` (batch at
     most 4 questions per call; issue further calls for any remaining
     items). If any answer comes back ambiguous or unresolved, don't guess —
     re-ask only those items before applying anything. Apply the answers:
     - **Add** → append the exact line to the named section of `profile.md`
       (create it first via `/project-profile`'s conventions if it doesn't
       exist yet); drop the item from the pending list.
     - **Defer** → leave the item in the pending list, untouched.
     - **Reject** → drop the item from the pending list permanently.
     Rewrite `profile-proposals.md` with whatever remains pending, or delete
     it if the queue is now empty. Record the per-item outcome for step 5.
   - **Unattended/scheduled run** (no one available to respond right now):
     skip the ask entirely. Append this session's new proposals to
     `profile-proposals.md` as pending (leave existing carried-over entries
     untouched) and record "profile: N new proposal(s) queued, unattended —
     no ask" for step 5. Never block waiting on an answer, and never write to
     `profile.md` on an unattended run.
5. Write `sessions/YYYY-MM-DD-<slug>.md` (the date/slug settled in step 2)
   containing:
   - **goal** — what this session set out to do;
   - **branch** and **commits made** (hashes + subjects);
   - **files changed** (paths only);
   - **tests/checks run** and their actual results;
   - **validation status** — green / red / not verified;
   - **decisions** — one line each, with the why (including any label
     reconciliation from step 3 and the profile-proposal outcome from
     step 4);
   - **risks** — what could bite a future session;
   - **deferred** — consciously not done;
   - **candidate workflow improvements** — answer each briefly: new reusable
     skill? existing skill to update? validation/check to add? privacy rule
     to add? nothing worth keeping? (profile updates are already resolved by
     step 4 — record the outcome, not a fresh suggestion.)
   - **next** — the single most useful next prompt.
6. Privacy pass: this note stays in the notes home, so local paths are fine —
   but confirm nothing session-private (transcripts, personal details) was
   left in *repo* files or staged changes. Flag anything you find; don't
   silently fix it.
   - If the user's closing note asks for the summary **in the repo or PR**
     (e.g. "save it as NOTES.md" / "so my teammate sees it"), do not write the
     note above into the repo. Follow the skill's **Repo-bound content**
     recipe: keep the full note in the notes home (step 5), then produce a
     *separate* sanitized summary and run `bin/check-private-info.sh` on it —
     block on the result — before leaving it (unstaged) in the repo.

Reply with the note's full path and the note itself. If the user wants a
paste-ready prompt for the next session, that's `/handoff` — offer it, don't
run it.
```

- [ ] **Step 2: Add the CHANGELOG entry**

Edit `CHANGELOG.md`, under `## [Unreleased]` → `### Changed` (add the heading if the section doesn't already have entries above `### Fixed`; otherwise prepend as the first bullet under the existing `### Changed`):

```markdown
- `/session-end` (draft — not yet pressure-tested): profile-worthy facts now
  go through a persistent `profile-proposals.md` Add/Defer/Reject queue
  instead of a one-line suggestion that got lost between sessions. Deferred
  proposals resurface at the next interactive `/session-end`; unattended runs
  queue new proposals without asking and never write to `profile.md`. See
  `docs/superpowers/specs/2026-07-13-profile-proposals-queue-design.md`.
```

- [ ] **Step 3: Verify structure**

Run (from the repo root): `make check`
Expected: `Hygiene checks PASSED` — frontmatter still valid, no broken links (the CHANGELOG references the spec doc's real path from Task 1's earlier commit), capability inventory unaffected.

- [ ] **Step 4: Commit**

```bash
git add commands/session-end.md CHANGELOG.md
git commit -m "feat(session-continuity): resolve profile proposals in /session-end via Add/Defer/Reject"
```

---

### Task 3: Register the pressure-test claim, then stop

**Files:**
- Modify: `skills/session-continuity/PRESSURE-TESTS.md` (new "## Claim 5" section; update the "## Not yet pressure-tested (still draft)" list at the end of the file)

**Interfaces:**
- Consumes: Task 2's new step-4 flow in `commands/session-end.md` (this is what the claim's RED/GREEN method will exercise once reps run).
- Produces: nothing consumed further within this plan — this is the terminal task, and it ends by stopping rather than running reps.

- [ ] **Step 1: Add the draft claim section**

Edit `skills/session-continuity/PRESSURE-TESTS.md`, inserting a new `## Claim 5` section immediately before the existing `## Closed mechanically (not a subagent claim)` heading:

```markdown
## Claim 5 — a deferred profile proposal persists and resurfaces at the next `/session-end` run

**Status: draft — not yet run.** Registered 2026-07-13 alongside the
profile-proposals queue implementation; reps are paused pending an explicit
user go-ahead on run mode (see `CONTRIBUTING.md`'s pressure-test convention:
sequential / parallel / defer-and-file-an-issue).

Claim: a profile-worthy fact that gets a **Defer** answer is not lost — it
reappears, unchanged, the next time `/session-end` runs interactively on the
same project. A **Reject** answer, by contrast, never reappears. This is the
core behavior the old one-line suggestion lacked (see the design spec,
`docs/superpowers/specs/2026-07-13-profile-proposals-queue-design.md`).

Proposed method (mirrors Claim 1's fixture style): a throwaway git repo
mimicking a mid-work session, plus a per-rep notes-home fixture directory
(`BINDLE_NOTES_DIR` override, per sub-claim 1c's methodology fix — every arm
gets its own override, not just GREEN). Two `/session-end` runs in sequence
against the same fixture, with a scripted **Defer** answer on the first run's
profile-proposal question:

| Variant | Setup | What to check |
|---|---|---|
| RED | no queue mechanism (pre-this-plan `/session-end`) | after the first run's suggestion is deferred verbally, does a *second* run re-surface the same fact? Expected baseline failure: no — it's gone, only in the first session's prose. |
| GREEN | this plan's `/session-end` + skill | first run: the fact is queued in `profile-proposals.md` and, on **Defer**, stays there untouched. Second run: the same entry is presented again for a decision. Filesystem is ground truth — diff `profile-proposals.md` between runs, and independently confirm `profile.md` is untouched by a deferred item. |

A second, smaller pass verifies **Reject**: a rejected item's line must not
appear in `profile-proposals.md` after the run that rejected it, on any
later run.
```

- [ ] **Step 2: Update the "Not yet pressure-tested" list**

Edit `skills/session-continuity/PRESSURE-TESTS.md`, in `## Not yet pressure-tested (still draft)`:

Old:
```
## Not yet pressure-tested (still draft)

- Nothing session-continuity-specific remains for Claim 1 (closed on Opus, Haiku,
  and Sonnet 5). The two items formerly listed here — the scanner denylist pass
  and an explicit-cleanup `/session-start` request — are closed by sub-claims 3c
  and 4a. Remaining weaker/mid-bracket gaps (Claims 2–4 on Haiku or Sonnet 5) are
  tracked in the operator's notes, not here.
```

New:
```
## Not yet pressure-tested (still draft)

- **Claim 5** (profile-proposals queue Add/Defer/Reject persistence) — method
  proposed, reps not yet run; paused pending the user's pressure-test
  run-mode choice per `CONTRIBUTING.md`.
- Nothing else session-continuity-specific remains for Claim 1 (closed on
  Opus, Haiku, and Sonnet 5). The two items formerly listed here — the
  scanner denylist pass and an explicit-cleanup `/session-start` request —
  are closed by sub-claims 3c and 4a. Remaining weaker/mid-bracket gaps
  (Claims 2–4 on Haiku or Sonnet 5) are tracked in the operator's notes, not
  here.
```

- [ ] **Step 3: Verify structure**

Run (from the repo root): `make check`
Expected: `Hygiene checks PASSED`.

- [ ] **Step 4: Commit**

```bash
git add skills/session-continuity/PRESSURE-TESTS.md
git commit -m "test(session-continuity): register Claim 5 — profile-proposals persistence (draft, not yet run)"
```

- [ ] **Step 5: STOP — do not run pressure-test reps**

The implementation (Tasks 1-2) and the draft claim (Task 3, steps 1-4) are
now committed on `feature/profile-proposals-queue`. Per this session's
explicit instruction, **do not execute Claim 5's reps now.** Report back to
the user that the plan is fully implemented and committed, and ask the
`CONTRIBUTING.md`-mandated question before any reps run: sequential
(recommended), parallel, or defer and file a `type: chore` /
`status: triage` GitHub issue (per `docs/issue-tracking.md`) to run them
later. Do not proceed past this point without that answer.
