# Converge facts store — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the `session-continuity` skill and its commands about a canonical per-fact `facts/` store — its format, the `profile.md` runbook-vs-pointer convention, and overwrite-in-place discipline for current-state facts — so the profile stops being a drift-prone monolith.

**Architecture:** All changes are Markdown contract edits. `skills/session-continuity/SKILL.md` is the source of truth (the three commands defer to it); `commands/session-end.md` and `commands/project-profile.md` get thin amendments that follow it. Behavioral claims are verified by Bindle's RED→GREEN→REFACTOR pressure-test loop (subagent reps graded on the filesystem), recorded in `skills/session-continuity/PRESSURE-TESTS.md`.

**Tech Stack:** Markdown (skill + commands); Bindle pressure-testing protocol (`docs/pressure-testing-protocol.md`); `bin/slugify.sh`; `make check`.

## Global Constraints

- **Design source of truth:** `docs/superpowers/specs/2026-07-23-converge-facts-store-design.md`. This plan implements **Phase 1 only**. Phase 2 (harness `memory/` symlink + portable Codex loader) is a separate future spec/plan.
- **Canonical fact format is Claude Code's harness schema, adopted verbatim** — nested `metadata.type` (vocab `feedback | project | reference | user`) and `metadata.modified` (ISO-8601 **datetime**, ms + `Z`); tolerate and never require `metadata.node_type` / `metadata.originSessionId`. Do not invent a competing schema.
- **Branch discipline:** work on `feature/422-converge-facts-store` (already cut off `main`, already carries the spec commit); never commit to `main`; `make check` green before every commit; never `--no-verify`.
- **Skill-change discipline:** a skill isn't done until pressure-tested (CONTRIBUTING); until then its `CHANGELOG` entry says **draft**. New `PRESSURE-TESTS.md` series must declare their arm and grade the transcript, not the self-report (`docs/pressure-testing-protocol.md`).
- **Pressure-test reps are deferred to #444.** The operator chose defer-and-file for this pass, so Phase 1 ships the contract edits as **draft** and the RED→GREEN campaign (Claims 7–9 below) runs under #444. The rep-dispatch steps in Tasks 2–4 stand as the campaign's spec; do not run them inline in this pass unless the operator reverses that.
- **The vault migration is not in this plan.** Deduping/thinning bindle's own `profile.md` in `$BINDLE_NOTES_DIR` produces no repo diff; it is post-merge dogfooding done by following the new contract.
- **Markdown link gate:** the link checker greps every bracket-then-parenthesis link file-wide (even inside code) and resolves the target relative to the file's dir. Never write a bare inline-link example (bracketed text immediately followed by a parenthesized path); describe link shapes in prose instead. Cross-doc refs use inline-code or a repo-absolute `/docs/...` path.

---

## File Structure

- **`skills/session-continuity/SKILL.md`** (modify) — the contract: add `facts/` to the notes-home layout; add a "Fact files" section (format + overwrite rule + `type: user` handling + `MEMORY.md` coexistence); rewrite the `profile.md` description as runbook-vs-pointer.
- **`commands/session-end.md`** (modify) — step 4 (profile proposals): route an `Add` to overwrite-in-place (current-state), pointer-to-`facts/` (shed), or inline (hot-core).
- **`commands/project-profile.md`** (modify) — the section list + the ~60-line rule: sections are runbook blocks or pointer lists; shed on-demand prose to `facts/`.
- **`skills/session-continuity/PRESSURE-TESTS.md`** (modify) — record the new claim series (or a deferral note).
- **`CHANGELOG.md`** — no hand edit (Release Please generates from Conventional Commits); the **draft** status rides in commit/PR prose.
- **`capabilities.json`** (modify) — one `not_a_capability` row for this plan doc.

---

### Task 1: Define the canonical `facts/` store in SKILL.md

Foundation. Pure definitional addition (no behavioral rep — it is the schema the later tasks reference). Verified by `make check` and read-back.

**Files:**
- Modify: `skills/session-continuity/SKILL.md` (the notes-home tree; a new "Fact files" section after it)

**Interfaces:**
- Produces: the `facts/` layout and the fact-file frontmatter schema that Tasks 2–4 reference by name (`metadata.type`, `metadata.modified`, `[[slug]]` pointers, `MEMORY.md` coexistence).

- [ ] **Step 1: Add `facts/` to the notes-home tree**

In `SKILL.md`'s "The notes home" code block, insert under `projects/<project>/` (after `profile-proposals.md`):

```
    facts/                            # canonical per-fact store — one durable fact per file
      MEMORY.md                       # Claude Code's auto-index (harness-managed)
      <fact-slug>.md                  # one fact; harness frontmatter schema (see "Fact files")
```

- [ ] **Step 2: Add the "Fact files (`facts/`)" section**

Insert a new section immediately after "The notes home":

````markdown
## Fact files (`facts/`)

A fact file holds one durable fact. Its format is **Claude Code's per-fact
memory schema, adopted verbatim**, so one physical store round-trips through the
harness unchanged — Bindle does not invent a competing schema.

```
---
name: <slug matching the filename>
description: "<one-line summary — used for relevance-loading>"
metadata:
  node_type: memory
  type: feedback | project | reference | user
  originSessionId: <uuid>            # harness-written; tolerate, never require
  modified: <ISO-8601 datetime, ms + Z, e.g. 2026-07-21T20:22:05.367Z>
---

<the fact>. For feedback/project facts, follow with **Why:** and
**How to apply:** lines. Link related facts with double-bracketed slugs.
```

- `type` and `modified` live **under `metadata`**, not at the top level.
- **`type: project` facts are current-state — overwrite them in place** with a
  fresh `metadata.modified`. Never append a correction or leave a
  strikethrough; the old value is gone, the file states only what is true now.
- `type: user` facts belong in global `~/.claude/CLAUDE.md`; a project-scoped
  one is advisory-misplaced — flag it, don't delete it. The type stays legal.
- `MEMORY.md` is Claude Code's flat auto-index; it coexists with `profile.md`.
  Both point at the same fact files; neither restates them.
- A fact's relations are double-bracketed slugs in the body; a pointer that
  names a not-yet-written fact is fine — it marks work, not an error.
````

(Write the relation syntax in prose as above — do not paste a bare markdown link, per the link gate.)

- [ ] **Step 3: Rewrite the `profile.md` description as runbook-vs-pointer**

Find where `SKILL.md` describes `profile.md` ("durable facts: gates, commands, safety notes"). Replace with:

```
    profile.md                        # curated runbook + pointer index — NOT a fact store
```

and add, in the prose that follows the tree:

```markdown
`profile.md` is a curated runbook + pointer index, not a fact store. Its seven
sections (unchanged, so the tooling contract holds) are each **either** a small
inline *runbook block* (the gate list, canonical commands — glance-before-you-
touch, loaded wholesale every session) **or** a *pointer list* of `[[fact]]`
+ a one-line hook (long-form safety notes, recurring instructions, context
locations). Keep a fact inline only if you need it in context **every** session;
shed on-demand reference to `facts/` and leave a pointer. profile.md points; it
does not restate.
```

- [ ] **Step 4: Run the gate**

Run: `make check`
Expected: PASS (frontmatter, links, formatting all green; the new section adds no bracket-then-parenthesis link syntax).

- [ ] **Step 5: Commit**

```bash
git add skills/session-continuity/SKILL.md
git commit -m "feat(#422): define canonical facts/ store in session-continuity"
```

---

### Task 2: profile.md runbook-vs-pointer behavior (project-profile + reps)

**Files:**
- Modify: `commands/project-profile.md` (section list + ~60-line rule)
- Modify: `skills/session-continuity/PRESSURE-TESTS.md` (new claim series)

**Interfaces:**
- Consumes: Task 1's `facts/` format and the profile pointer convention.
- Produces: the behavior Task 3/4 build on — a session that sheds on-demand prose to `facts/` and keeps only the hot core inline.

- [ ] **Step 1: Amend `project-profile.md` step 3**

In the "Write/refresh these sections" list, add a lead-in sentence before the seven bullets:

```markdown
   Each section is **either** an inline runbook block **or** a pointer list of
   `[[fact]]` + one-line hook (see the session-continuity skill's "Fact files").
   Keep gates and common commands inline; shed long-form safety-note and
   recurring-instruction prose to `facts/` and point at it.
```

- [ ] **Step 2: Amend `project-profile.md` step 4 (the size rule)**

Replace the "Keep it under ~60 lines" sentence with:

```markdown
4. Keep the inline runbook under ~60 lines. On-demand reference goes to
   `facts/` as `[[fact]]` pointers, not inline prose — profile.md shrinks as
   facts atomize. Facts the project's own README/provider guidance already
   states get a pointer, not a copy.
```

- [ ] **Step 3: Declare the RED arm and pressure scenario**

In `PRESSURE-TESTS.md`, append a new claim section (draft, arm declared per the protocol):

```markdown
## Claim 7 — /project-profile sheds on-demand facts to pointers (Rule: runbook-vs-pointer)

**Status: DRAFT — arm declared, reps pending.**

Arm: the session-continuity `/project-profile` skill+command. Scenario: a fixture
notes home whose `profile.md` has a fat "safety notes" section (5+ lines of
long-form prose) plus a lean gate list; ask the agent to refresh the profile.
RED = no skill; GREEN = real `/project-profile` + skill.

Predicted RED failure: agent rewrites all sections as inline prose, no `facts/`
files, no pointers. GREEN: gate list stays inline; the long-form safety prose
becomes `facts/<slug>.md` files (harness schema) + `[[slug]]` pointers in
profile.md; profile.md line count drops.
```

- [ ] **Step 4: Run the reps (operator-gated)**

Ask the operator: **sequential / parallel / defer-and-file-issue** (CONTRIBUTING). Then, per `docs/pressure-testing-protocol.md`: run the pre-dispatch fixture checklist, give each rep its own fixture copy, confirm the skill is absent for RED (probe "Unknown skill"), dispatch ~5 reps/variant, and grade the transcript + filesystem (`grep '"name":"Skill"'` in `tasks/<id>.output`), not the self-report.

Expected RED: majority write inline prose, no `facts/`. Expected GREEN: majority shed to `facts/` + pointers with the correct schema.

Deferred to #444 in this pass: leave Claim 7 **DRAFT** and record the deferral (pointing at #444) in `PRESSURE-TESTS.md`.

- [ ] **Step 5: Record results and commit**

Fill Claim 7's result table (or the deferral note). Run `make check`.

```bash
git add commands/project-profile.md skills/session-continuity/PRESSURE-TESTS.md
git commit -m "feat(#422): profile runbook-vs-pointer convention for /project-profile"
```

---

### Task 3: Overwrite-in-place discipline for current-state facts (session-end + reps)

The marquee drift-killer — ends the stacked-strikethrough pathology.

**Files:**
- Modify: `commands/session-end.md` (step 4 Add handling)
- Modify: `skills/session-continuity/PRESSURE-TESTS.md` (new claim series)

**Interfaces:**
- Consumes: Task 1's `type: project` overwrite rule and fact schema.

- [ ] **Step 1: Amend `session-end.md` step 4 — the `Add` branch**

Find the "**Add** → append the exact line to the named section of `profile.md`" bullet. Replace it with:

```markdown
     - **Add** → route by the fact's kind (see the skill's "Fact files"):
       - **Current-state (`type: project`)** — write or **overwrite in place**
         `facts/<slug>.md` with a fresh `metadata.modified`; put a `[[slug]]`
         pointer in profile.md if not already present. Never append a corrected
         line or leave a strikethrough — the file states only what is true now.
       - **On-demand reference** (long-form safety / recurring / context prose)
         — write `facts/<slug>.md` (harness schema) and append a `[[slug]]`
         pointer to the named profile.md section, not the full prose.
       - **Hot core** (a must-load-every-session gate or one-liner) — append the
         exact line inline to the named profile.md section (create the section
         via `/project-profile`'s conventions if absent).
       Drop the item from the pending list in every case.
```

- [ ] **Step 2: Declare the RED arm and pressure scenario**

Append to `PRESSURE-TESTS.md`:

```markdown
## Claim 8 — /session-end overwrites current-state facts in place (Rule: no strikethrough)

**Status: DRAFT — arm declared, reps pending.**

Arm: the session-continuity `/session-end` skill+command. Scenario: a fixture
notes home holding a `facts/<slug>.md` with `type: project` (e.g. "prod: armed")
and a matching profile pointer; the session's work flips the state ("prod:
disarmed"). Ask the agent to close the session and record the change. RED = no
skill; GREEN = real `/session-end` + skill.

Predicted RED failure: agent appends a strikethrough or a stacked correction
(old value retained). GREEN: the fact file is overwritten in place, old value
gone, `metadata.modified` bumped; no strikethrough anywhere.
```

- [ ] **Step 3: Run the reps (operator-gated)**

Same gating and grading as Task 2 Step 4 (ask sequential/parallel/defer; fixture checklist; grade filesystem — assert the fact file's body contains the new value and **not** the old one, and carries no `~~strikethrough~~`). If deferred, leave DRAFT and file/record per Task 2 Step 4.

- [ ] **Step 4: Record results and commit**

```bash
git add commands/session-end.md skills/session-continuity/PRESSURE-TESTS.md
git commit -m "feat(#422): overwrite-in-place discipline for current-state facts"
```

---

### Task 4: Atomize-on-touch migration rule (session-end + reps)

**Files:**
- Modify: `skills/session-continuity/SKILL.md` (a "Migration — convert-on-touch" note)
- Modify: `commands/session-end.md` (step 5 or a note in step 4)
- Modify: `skills/session-continuity/PRESSURE-TESTS.md`

**Interfaces:**
- Consumes: Task 1 fact schema; Task 3's `Add` routing.

- [ ] **Step 1: Add the migration rule to SKILL.md**

After the "Fact files" section, add:

```markdown
### Migration — convert-on-touch (no big-bang)

profile.md shrinks monotonically; there is no flag day. When a session **edits**
a fact that currently lives as inline profile.md prose but is on-demand
reference by nature, atomize it: move it to `facts/<slug>.md` and leave a
`[[slug]]` pointer behind. Touching a fact is the trigger; untouched prose stays
until a session next needs it. Never do a bulk rewrite as a side effect.
```

- [ ] **Step 2: Cross-reference from `session-end.md`**

In `session-end.md` step 4, after the `Add` routing bullet, add:

```markdown
     Convert-on-touch: if applying an Add means editing a fact that still lives
     as inline profile.md prose and is on-demand by nature, atomize it to
     `facts/` + a pointer rather than editing it in place inline (see the
     skill's "Migration — convert-on-touch").
```

- [ ] **Step 3: Declare the arm; run reps or fold into Claim 7**

Atomize-on-touch shares the shed-vs-inline judgment with Claim 7. Either extend Claim 7 with a "convert-on-touch" variant (a fixture where an *existing* inline fact is edited) or declare a separate Claim 9. Prefer folding into Claim 7 to save reps (scale-review-to-stakes). Record which in `PRESSURE-TESTS.md`; operator-gated dispatch as in Task 2 Step 4.

- [ ] **Step 4: Run gate and commit**

Run: `make check`

```bash
git add skills/session-continuity/SKILL.md commands/session-end.md skills/session-continuity/PRESSURE-TESTS.md
git commit -m "feat(#422): convert-on-touch atomization for session-continuity facts"
```

---

### Task 5: Housekeeping — ledger, draft status, whole-suite gate

**Files:**
- Modify: `capabilities.json` (one `not_a_capability` row for this plan doc)

- [ ] **Step 1: Add the plan doc to the ledger**

Textually insert (never a `json.load`/`dumps` round-trip — it reorders the ledger) after the spec's row in the `not_a_capability` array:

```json
    {
      "path": "docs/superpowers/plans/2026-07-23-converge-facts-store-phase1.md",
      "reason": "a point-in-time implementation plan for Phase 1 of the facts-store convergence (#422), paired with its design spec; planning artifact, not itself a capability."
    }
```

- [ ] **Step 2: Confirm draft status is honest**

If any of Claims 7–9 are still DRAFT (reps deferred), the PR body and commit prose must say the skill change is **draft pending pressure-test** (CONTRIBUTING's "Draft vs. tested"). Do not describe it as verified.

- [ ] **Step 3: Full local gate**

Run (foreground, generous timeout — the discovered suites can approach ~90s):
```bash
make check && bin/run-test-suites.sh
```
Expected: both green. `make check` alone does **not** run the discovered `bin/test-*.sh` suites.

- [ ] **Step 4: Commit**

```bash
git add capabilities.json
git commit -m "docs(#422): record Phase 1 plan in the capability ledger"
```

---

## Out of scope (Phase 2 / not this plan)

> **Premise correction (measured 2026-07-25), for whoever plans Phase 2.** This
> plan and the design it implements assumed the harness auto-loads the per-fact
> store "by relevance." It does not: it injects the `MEMORY.md` **index**, and
> fact bodies are never auto-injected — in a symlinked *and* a real `memory/`
> dir alike. Nothing in Phase 1 depends on that assumption (Phase 1 is a
> format-and-discipline change), but both Phase 2 items below were scoped
> against it. See the design doc's "Risks and open validation items".

- The harness `memory/` → vault `facts/` **symlink** and its validation step.
  Measured: reads through the symlink work, interactive writes work, **headless
  writes are refused**, and write-time frontmatter enrichment is lost.
- The **portable Codex loader** in the command layer. Given the correction above,
  this is the only mechanism on the table that proactively surfaces fact
  *bodies* — and it does so for Claude as well as Codex.
- The frontmatter **lint** (#423) — it enforces the schema this plan freezes.
- **Vault migration** of bindle's own profile — private-data dogfooding, no repo diff.
- Any **SQLite/derived index** — Markdown stays canonical.

## Self-review notes

- **Spec coverage:** Phase 1's four parts map to Tasks 1 (format freeze), 2 (conservative thinning / pointer convention), 3 (overwrite discipline), 4 (atomize-on-touch). Single-home dedup + thinning of bindle's own profile is explicitly out (vault data). #423 coupling is carried in the Global Constraints + Out-of-scope. ✔
- **Type consistency:** `metadata.type` / `metadata.modified` / `[[slug]]` pointer / `facts/<slug>.md` used identically across Tasks 1–4. ✔
- **No placeholders:** each edit shows the exact prose to insert; `<slug>` / `<uuid>` are format placeholders in a schema, not TODOs. ✔
